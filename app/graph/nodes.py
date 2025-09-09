from __future__ import annotations
import os, uuid, asyncio
import time, logging
from typing import List, Dict

logger = logging.getLogger("ai_mvp")
if not logger.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

from rapidfuzz import fuzz
from app.models import (
    PressPlan, RecordModel, ScreeningModel, AppraisalModel, PrismaCountsModel
)
from app.rubric import Rubric
from app.ai_service import get_ai_service
from app.publication_classifier import batch_classify_publications
from app.sources import (
    pubmed_search_async, crossref_search_async, arxiv_search_async, eric_search_async,
    s2_search_async, scholar_serpapi_async,
)

_RUBRIC = None

def plan_press(state):
    t0 = time.perf_counter()

    # fresh run_id per invocation; keep thread memory
    state["run_id"] = str(uuid.uuid4())
    state["prisma"] = PrismaCountsModel()
    state["records"] = []
    state["screenings"] = []
    state["appraisals"] = []
    state["seen_external_ids"] = state.get("seen_external_ids") or []

    # ensure observability dicts exist
    state["timings"] = state.get("timings") or {}
    state["source_counts"] = state.get("source_counts") or {}

    # If a PRESS plan is already provided (e.g., via LICO run), keep it; otherwise create a default
    q = (state.get("query") or "instructional design evidence synthesis").strip()
    if not state.get("press"):
        year_min = os.getenv("PRESS_YEAR_MIN", "2019-")
        state["press"] = PressPlan(
            concepts=[q],
            boolean=f'("{q}"[Title/Abstract]) AND (study OR trial OR evaluation)',
            sources=["PubMed", "Crossref", "ERIC", "SemanticScholar", "GoogleScholar", "arXiv"],
            years=year_min,
        )

    state["timings"]["plan_press"] = round(time.perf_counter() - t0, 6)
    logger.info("plan_press: query='%s'", q)
    return state


def _dedupe_records(recs: List[RecordModel]) -> List[RecordModel]:
    out: List[RecordModel] = []
    seen_keys = set()
    for r in recs:
        key = (r.doi or r.record_id or "").lower()
        title = (r.title or "").lower()
        if key and key in seen_keys:
            continue
        if any(fuzz.token_set_ratio(title, o.title.lower()) >= 96 for o in out):
            continue
        out.append(r)
        if key:
            seen_keys.add(key)
    return out


def harvest(state):
    t0 = time.perf_counter()
    q = (state.get("query") or "instructional design evidence synthesis").strip()
    mailto = os.getenv("CROSSREF_MAILTO")

    # PRESS year filter like "2019-"
    year_min = None
    years = state["press"].years if state.get("press") else None
    if isinstance(years, str) and years.endswith("-"):
        try:
            year_min = int(years[:-1])
        except Exception:
            pass

    # Respect configured sources from PRESS plan if provided
    wanted = set()
    try:
        press = state.get("press")
        if press and getattr(press, "sources", None):
            wanted = set([s.strip() for s in press.sources or []])
    except Exception:
        wanted = set()

    # Map source name -> coroutine to fetch
    coros = []
    def add(name, coro):
        if not wanted or name in wanted:
            coros.append(coro)

    add("PubMed", pubmed_search_async(q, max_n=25))
    add("Crossref", crossref_search_async(q, max_n=25, mailto=mailto))
    add("arXiv", arxiv_search_async(q, max_n=25))
    add("ERIC", eric_search_async(q, max_n=25))
    add("SemanticScholar", s2_search_async(q, max_n=25))
    add("GoogleScholar", scholar_serpapi_async(q, max_n=25, year_min=year_min))  # pass year floor

    async def gather():
        return await asyncio.gather(*coros, return_exceptions=True)

    res = asyncio.run(gather())

    # Count identified per source (pre-filters)
    per_src: Dict[str, int] = {}
    flattened = []
    for batch in res:
        if isinstance(batch, Exception) or not batch:
            continue
        for r in batch:
            src = (r.get("source") or "Unknown").strip()
            per_src[src] = per_src.get(src, 0) + 1
            flattened.append(r)

    # Skip thread-seen items
    seen = set(state.get("seen_external_ids") or [])
    filtered_seen = [r for r in flattened if (r.get("record_id") or "") not in seen]

    # PRESS year filter like "2019-"
    year_min = None
    years = state["press"].years if state.get("press") else None
    if isinstance(years, str) and years.endswith("-"):
        try:
            year_min = int(years[:-1])
        except Exception:
            pass
    filtered = [r for r in filtered_seen if year_min is None or (r.get("year") or 0) >= year_min]

    # Add AI-powered publication type classification
    try:
        logger.info("harvest: classifying publication types for %d records", len(filtered))
        classifications = batch_classify_publications(filtered)
        
        # Apply classifications to records
        for record in filtered:
            record_id = record.get("record_id", "")
            if record_id in classifications:
                record["publication_type"] = classifications[record_id]
            else:
                record["publication_type"] = "Unknown"
        
        logger.info("harvest: publication type classification completed")
    except Exception as e:
        logger.warning(f"harvest: publication type classification failed: {e}")
        # Set fallback publication types
        for record in filtered:
            record["publication_type"] = "Unknown"

    # Validate to models
    state["records"] = [RecordModel.model_validate(r) for r in filtered]

    # Update PRISMA and observability
    identified_count = sum(per_src.values())
    pc = state.get("prisma") or PrismaCountsModel()
    pc.identified += identified_count
    state["prisma"] = pc

    state["source_counts"] = per_src
    state["timings"] = state.get("timings") or {}
    state["timings"]["harvest"] = round(time.perf_counter() - t0, 6)
    logger.info(
        "harvest: per_source=%s kept=%d identified=%d",
        per_src, len(state["records"]), identified_count
    )
    return state


async def _screen_record(record: RecordModel, use_ai: bool = False, inclusion_criteria: list = None, exclusion_criteria: list = None) -> tuple[str, str]:
    """Apply inclusion/exclusion criteria to a single record."""
    # Try AI screening first if enabled
    if use_ai:
        ai_service = get_ai_service()
        if ai_service.is_available():
            try:
                # Default criteria if not provided
                default_inclusion = [
                    "Published 2018 or later",
                    "Primary research studies",
                    "Human subjects",
                    "English language",
                    "Related to education or healthcare training"
                ]
                default_exclusion = [
                    "Pre-2018 publication",
                    "Animal studies", 
                    "Editorial, commentary, or opinion pieces",
                    "Non-English publications",
                    "Not relevant to research question"
                ]
                
                assessment = await ai_service.assess_study_relevance(
                    title=record.title or "",
                    abstract=record.abstract,
                    inclusion_criteria=inclusion_criteria or default_inclusion,
                    exclusion_criteria=exclusion_criteria or default_exclusion
                )
                
                if assessment:
                    if assessment.inclusion_recommendation == "exclude":
                        return "exclude", assessment.exclusion_reason or "AI screening"
                    elif assessment.inclusion_recommendation == "include":
                        return "include", ""
                    # If "uncertain", fall through to rule-based screening
                        
            except Exception as e:
                logger.warning(f"AI screening failed for record {record.record_id}: {e}")
                # Fall through to rule-based screening
    
    # Rule-based screening (original logic)
    # Publication year criteria
    if (record.year or 0) < 2018:
        return "exclude", "Pre-2018"
    
    # Check for non-English content (basic heuristic)
    title = (record.title or "").lower()
    abstract = (record.abstract or "").lower()
    combined_text = f"{title} {abstract}"
    
    # Check for study types that are typically excluded
    if any(term in combined_text for term in ["editorial", "letter to", "commentary", "opinion", "book review", "conference abstract"]):
        return "exclude", "Study type"
    
    # Check for animal studies (if this is a human-focused review)
    animal_terms = ["animal", "mice", "rats", "mouse", "pig", "sheep", "dog", "cat", "rabbit", "primate", "bovine", "porcine", "murine", "rodent"]
    human_terms = ["human", "patient", "participant", "subject", "clinical", "hospital", "nursing", "medical student"]
    
    animal_count = sum(1 for term in animal_terms if term in combined_text)
    human_count = sum(1 for term in human_terms if term in combined_text)
    
    if animal_count > human_count and animal_count > 2:
        return "exclude", "Animal study"
    
    # Check for non-research content
    if any(term in combined_text for term in ["review", "systematic review", "meta-analysis", "guidelines", "recommendations"]):
        # Allow systematic reviews but exclude other types of reviews
        if "systematic review" not in combined_text and "meta-analysis" not in combined_text:
            if "review" in combined_text and len([t for t in ["research", "study", "trial", "experiment"] if t in combined_text]) < 2:
                return "exclude", "Not primary research"
    
    # Check for language (basic check for non-Latin scripts)
    if any(ord(char) > 1000 for char in title[:100]):  # Basic check for non-Latin characters
        return "exclude", "Non-English"
    
    # Check for relevance to education/learning (context-specific)
    education_terms = ["education", "teaching", "learning", "training", "curriculum", "student", "academic", "school"]
    if not any(term in combined_text for term in education_terms) and len(combined_text) > 100:
        # Only exclude if there's substantial content but no educational terms
        return "exclude", "Not relevant"
    
    return "include", ""


async def dedupe_screen(state):
    t0 = time.perf_counter()

    recs: List[RecordModel] = state.get("records", [])
    deduped = _dedupe_records(recs)
    
    # Check if AI screening is enabled (can be set in state)
    use_ai_screening = state.get("use_ai_screening", False)
    inclusion_criteria = state.get("inclusion_criteria")
    exclusion_criteria = state.get("exclusion_criteria")

    screenings: List[ScreeningModel] = []
    kept: List[RecordModel] = []
    
    # Process records (potentially in parallel for AI screening)
    if use_ai_screening:
        # Process with AI assistance
        tasks = []
        import asyncio
        for r in deduped:
            task = _screen_record(r, use_ai=True, inclusion_criteria=inclusion_criteria, exclusion_criteria=exclusion_criteria)
            tasks.append(task)
        
        screening_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r, result in zip(deduped, screening_results):
            if isinstance(result, Exception):
                logger.warning(f"Screening failed for record {r.record_id}: {result}")
                # Fall back to rule-based screening
                decision, reason = await _screen_record(r, use_ai=False)
            else:
                decision, reason = result
                
            screenings.append(ScreeningModel(record_id=r.record_id, decision=decision, reason=reason))
            if decision == "include":
                kept.append(r)
    else:
        # Standard rule-based screening
        for r in deduped:
            decision, reason = await _screen_record(r, use_ai=False)
            screenings.append(ScreeningModel(record_id=r.record_id, decision=decision, reason=reason))
            if decision == "include":
                kept.append(r)

    pc = state.get("prisma") or PrismaCountsModel()
    pc.deduped = len(deduped)
    pc.screened = len(deduped)
    pc.excluded = sum(1 for s in screenings if s.decision == "exclude")
    pc.eligible = len(kept)

    state["records"] = kept
    state["screenings"] = screenings
    state["prisma"] = pc

    state["timings"] = state.get("timings") or {}
    state["timings"]["dedupe_screen"] = round(time.perf_counter() - t0, 6)
    logger.info(
        "dedupe_screen: deduped=%d screened=%d excluded=%d kept=%d",
        pc.deduped, pc.screened, pc.excluded, pc.eligible
    )
    return state


async def appraise(state):
    t0 = time.perf_counter()
    global _RUBRIC
    if _RUBRIC is None:
        _RUBRIC = Rubric.load("rubric.yaml")

    # Check if AI rationale generation is enabled
    use_ai_rationale = state.get("use_ai_rationale", False)
    ai_service = get_ai_service() if use_ai_rationale else None

    apps: List[AppraisalModel] = []
    for r in state.get("records", []):
        rating, scores = _RUBRIC.rate(r.year, r.title, r.abstract)
        
        # Generate AI rationale if enabled and available
        rationale = "Quality assessment based on rubric criteria"
        if use_ai_rationale and ai_service and ai_service.is_available():
            try:
                ai_rationale = await ai_service.generate_quality_rationale(
                    title=r.title or "",
                    abstract=r.abstract,
                    year=r.year,
                    rating=rating,
                    scores=scores
                )
                if ai_rationale:
                    rationale = ai_rationale
            except Exception as e:
                logger.warning(f"AI rationale generation failed for record {r.record_id}: {e}")
                # Use default rationale
        
        apps.append(AppraisalModel(
            record_id=r.record_id,
            rating=rating,
            rationale=rationale,
            scores={k: float(v) for k, v in scores.items()},
            citations=[r.url or ""],
        ))

    pc = state.get("prisma") or PrismaCountsModel()
    pc.included = len(apps)

    state["appraisals"] = apps
    state["prisma"] = pc

    state["timings"] = state.get("timings") or {}
    state["timings"]["appraise"] = round(time.perf_counter() - t0, 6)
    logger.info("appraise: n_appraised=%d", len(apps))
    return state


def report_prisma(state):
    t0 = time.perf_counter()

    # remember kept IDs for this thread
    kept_ids = [r.record_id for r in state.get("records", [])]
    seen = state.get("seen_external_ids") or []
    state["seen_external_ids"] = list({*seen, *kept_ids})

    state["timings"] = state.get("timings") or {}
    state["timings"]["report_prisma"] = round(time.perf_counter() - t0, 6)
    return state
