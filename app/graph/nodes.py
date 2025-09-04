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

    q = (state.get("query") or "instructional design evidence synthesis").strip()
    state["press"] = PressPlan(
        concepts=[q],
        boolean=f'("{q}"[Title/Abstract]) AND (study OR trial OR evaluation)',
        sources=["PubMed", "Crossref"],
        years="2019-",
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

    async def gather():
        return await asyncio.gather(
            pubmed_search_async(q, max_n=25),
            crossref_search_async(q, max_n=25, mailto=mailto),
            arxiv_search_async(q, max_n=25),
            eric_search_async(q, max_n=25),
            s2_search_async(q, max_n=25),
            scholar_serpapi_async(q, max_n=25, year_min=year_min),  # <-- pass year floor
            return_exceptions=True,
        )

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


def dedupe_screen(state):
    t0 = time.perf_counter()

    recs: List[RecordModel] = state.get("records", [])
    deduped = _dedupe_records(recs)

    screenings: List[ScreeningModel] = []
    kept: List[RecordModel] = []
    for r in deduped:
        if (r.year or 0) < 2018:
            screenings.append(ScreeningModel(record_id=r.record_id, decision="exclude", reason="Pre-2018"))
        else:
            screenings.append(ScreeningModel(record_id=r.record_id, decision="include", reason=""))
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


def appraise(state):
    t0 = time.perf_counter()
    global _RUBRIC
    if _RUBRIC is None:
        _RUBRIC = Rubric.load("rubric.yaml")

    apps: List[AppraisalModel] = []
    for r in state.get("records", []):
        rating, scores = _RUBRIC.rate(r.year, r.title, r.abstract)
        apps.append(AppraisalModel(
            record_id=r.record_id,
            rating=rating,
            scores={k: float(v) for k, v in scores.items() if k != "final"},
            rationale=f"Weighted scores → final={scores['final']:.2f} via rubric.yaml",
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
