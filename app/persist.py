from __future__ import annotations
import json
import sys
from typing import Dict, Any, Optional
from uuid import uuid4
from app.db import (
    init_db,
    get_session,
    SearchRun,
    Record,
    Appraisal,
    PrismaCounts,
    Screening,
)
from app.models_extended import (
    AppraisalMethodology,
    MultiMethodAppraisal,
    AppraisalMethodType,
    create_default_methodologies
)

def safe_print(message):
    """Print messages safely, handling Unicode characters that might not be encodable."""
    try:
        print(message)
    except UnicodeEncodeError:
        # Replace problematic characters and try again
        safe_message = message.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
        print(safe_message)

def update_run_progress(
    run_id: str,
    current_stage: Optional[str] = None,
    stage_progress: Optional[float] = None,
    total_records: Optional[int] = None,
    processed_records: Optional[int] = None
) -> None:
    """Update progress tracking fields for a running workflow.

    Args:
        run_id: The run ID to update
        current_stage: Stage name (planning, harvesting, screening, appraisal, reporting, completed)
        stage_progress: Progress within current stage (0.0 to 1.0)
        total_records: Total number of records to process
        processed_records: Number of records processed so far
    """
    try:
        init_db()
        with get_session() as s:
            run = s.get(SearchRun, run_id)
            if run is None:
                # Run doesn't exist yet - create it
                run = SearchRun(id=run_id, query="")
                s.add(run)

            if current_stage is not None:
                run.current_stage = current_stage
            if stage_progress is not None:
                run.stage_progress = max(0.0, min(1.0, stage_progress))  # Clamp to 0-1
            if total_records is not None:
                run.total_records = total_records
            if processed_records is not None:
                run.processed_records = processed_records

            s.commit()
    except Exception as e:
        # Don't let progress tracking errors crash the workflow
        safe_print(f"WARNING: Failed to update progress for run {run_id}: {e}")

def _get_attr(obj, key, default=None):
    """Read from a Pydantic model OR a plain dict."""
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default

def _extract_title_from_id(ext_id: str) -> str:
    """Extract a better title from external ID when no metadata is available."""
    if not ext_id:
        return "Unknown Record"

    # Remove common prefixes to get cleaner IDs
    if ext_id.startswith("doi:"):
        clean_id = ext_id[4:]
    elif ext_id.startswith("pmid:"):
        clean_id = ext_id[5:]
        return f"PubMed Article {clean_id}"
    elif ext_id.startswith("arxiv:"):
        clean_id = ext_id[6:]
        return f"arXiv Paper {clean_id}"
    elif ext_id.startswith("eric:"):
        clean_id = ext_id[5:]
        return f"ERIC Document {clean_id}"
    elif ext_id.startswith("s2:"):
        clean_id = ext_id[:20] + "..."  # Truncate long semantic scholar IDs
        return f"Semantic Scholar Paper {clean_id}"
    elif ext_id.startswith("scholar:"):
        clean_id = ext_id[:20] + "..."  # Truncate long google scholar IDs
        return f"Google Scholar Paper {clean_id}"
    else:
        clean_id = ext_id

    # For DOIs, try to extract journal/publisher info
    if "/" in clean_id and "." in clean_id:
        return f"Journal Article {clean_id}"

    return f"Research Paper {clean_id}"

def _extract_source_from_id(ext_id: str) -> str:
    """Extract source database from external ID."""
    if not ext_id:
        return "Unknown"

    if ext_id.startswith("doi:"):
        return "CrossRef/DOI"
    elif ext_id.startswith("pmid:"):
        return "PubMed"
    elif ext_id.startswith("arxiv:"):
        return "arXiv"
    elif ext_id.startswith("eric:"):
        return "ERIC"
    elif ext_id.startswith("s2:"):
        return "Semantic Scholar"
    elif ext_id.startswith("scholar:"):
        return "Google Scholar"
    else:
        return "Unknown"

def persist_run(state: Dict[str, Any]) -> str:
    safe_print("DEBUG persist_run: FUNCTION CALLED!")  # Force visible output
    init_db()
    run_id = state.get("run_id") or str(uuid4())

    with get_session() as s:
        # Check if run already exists (from progress tracking)
        existing_run = s.get(SearchRun, run_id)
        if existing_run is not None:
            # Update existing run with final query
            run = existing_run
            run.query = state.get("query", "")
            safe_print(f"DEBUG persist_run: Updating existing run {run_id} with query data")
        else:
            # Create new run row
            run = SearchRun(id=run_id, query=state.get("query", ""))
            s.add(run)
            safe_print(f"DEBUG persist_run: Creating new run {run_id}")
        s.flush()

        # Get records and screening data
        original_records = state.get("original_records", []) or []
        included_records = state.get("records", []) or []
        screenings = state.get("screenings", []) or []

        safe_print(f"DEBUG persist_run: Found {len(original_records)} original records with metadata")
        safe_print(f"DEBUG persist_run: Found {len(included_records)} included records")
        safe_print(f"DEBUG persist_run: Found {len(screenings)} screening decisions")

        # Debug: check what included_records look like
        safe_print(f"DEBUG included_records type: {type(included_records)}")
        safe_print(f"DEBUG included_records length: {len(included_records) if included_records else 'None/empty'}")
        if included_records and len(included_records) > 0:
            safe_print(f"DEBUG first included_record type: {type(included_records[0])}")
            safe_print(f"DEBUG first included_record keys: {list(included_records[0].keys()) if hasattr(included_records[0], 'keys') else 'No keys method'}")
            safe_print(f"DEBUG first included_record dir: {[x for x in dir(included_records[0]) if not x.startswith('_')][:10]}")

        for i, rec in enumerate(included_records[:2]):
            ext_id = _get_attr(rec, "record_id", "NO_ID")
            title = _get_attr(rec, "title", "NO_TITLE")[:30]
            safe_print(f"DEBUG included_record[{i}]: id='{ext_id}', title='{title}...'")

        # Debug: check what screenings look like
        for i, scr in enumerate(screenings[:2]):
            ext_id = _get_attr(scr, "record_id", "NO_ID")
            decision = _get_attr(scr, "decision", "NO_DECISION")
            safe_print(f"DEBUG screening_sample[{i}]: id='{ext_id}', decision='{decision}'")

        # Enhanced debug logging for excluded records specifically
        excluded_screenings = [s for s in screenings if _get_attr(s, "decision", "") == "exclude"]
        included_screenings = [s for s in screenings if _get_attr(s, "decision", "") == "include"]
        safe_print(f"DEBUG persist_run: Found {len(excluded_screenings)} excluded screenings")
        safe_print(f"DEBUG persist_run: Found {len(included_screenings)} included screenings")

        # Sample excluded screening decisions
        for i, exc_scr in enumerate(excluded_screenings[:3]):
            ext_id = _get_attr(exc_scr, "record_id", "NO_ID")
            reason = _get_attr(exc_scr, "reason", "NO_REASON")[:50]
            safe_print(f"DEBUG persist_run: EXCLUDED screening[{i}]: id='{ext_id}', reason='{reason}...'")

        # Sample included screening decisions
        for i, inc_scr in enumerate(included_screenings[:3]):
            ext_id = _get_attr(inc_scr, "record_id", "NO_ID")
            reason = _get_attr(inc_scr, "reason", "NO_REASON")[:50]
            safe_print(f"DEBUG persist_run: INCLUDED screening[{i}]: id='{ext_id}', reason='{reason}...'")

        # Strategy: Build a comprehensive record set from all available sources
        all_records_data = {}

        # First, add records from original_records (preferred - has full metadata for all records INCLUDING excluded)
        safe_print(f"DEBUG persist_run: Processing {len(original_records)} original_records")
        for i, record in enumerate(original_records):
            ext_id = _get_attr(record, "record_id", "") or ""
            if ext_id:
                # Convert Pydantic model to dict for consistent handling
                if hasattr(record, 'model_dump'):
                    # Pydantic v2
                    record_dict = record.model_dump()
                elif hasattr(record, 'dict'):
                    # Pydantic v1
                    record_dict = record.dict()
                elif isinstance(record, dict):
                    record_dict = record
                else:
                    # Fallback: use the object directly
                    record_dict = record

                all_records_data[ext_id] = record_dict
                title = _get_attr(record_dict, "title", "")
                title_preview = title[:50] if title else "NO_TITLE"
                authors = _get_attr(record_dict, "authors", "")
                authors_preview = authors[:30] if authors else "NO_AUTHORS"
                safe_print(f"DEBUG Added original_record[{i}]: id='{ext_id}', title='{title_preview}...', authors='{authors_preview}...'")

        # ENHANCED FALLBACK: If original_records is empty (workflow issue), use included_records
        # This should rarely happen if dedupe_screen is working correctly
        if len(original_records) == 0:
            safe_print(f"DEBUG persist_run: WARNING - original_records is empty! Using included_records fallback (will lose excluded record metadata)")
            if len(included_records) > 0:
                safe_print(f"DEBUG persist_run: FALLBACK MODE - using {len(included_records)} included_records")

                # Use included_records for all records that have metadata
                for i, record in enumerate(included_records):
                    ext_id = _get_attr(record, "record_id", "") or ""
                    if ext_id:
                        # Convert to dict
                        if hasattr(record, 'model_dump'):
                            record_dict = record.model_dump()
                        elif hasattr(record, 'dict'):
                            record_dict = record.dict()
                        elif isinstance(record, dict):
                            record_dict = record
                        else:
                            record_dict = record

                        all_records_data[ext_id] = record_dict
                        title = _get_attr(record_dict, "title", "")[:50]
                        safe_print(f"DEBUG Added included_record[{i}]: id='{ext_id}', title='{title}...'")

        # For any remaining screenings without record data, create minimal placeholders
        screening_ids = set()
        excluded_screening_ids = set()
        included_screening_ids = set()
        for screening in screenings:
            ext_id = _get_attr(screening, "record_id", "") or ""
            decision = _get_attr(screening, "decision", "")
            if ext_id:
                screening_ids.add(ext_id)
                if decision == "exclude":
                    excluded_screening_ids.add(ext_id)
                elif decision == "include":
                    included_screening_ids.add(ext_id)

        safe_print(f"DEBUG persist_run: Total screening IDs: {len(screening_ids)}")
        safe_print(f"DEBUG persist_run: Excluded screening IDs: {len(excluded_screening_ids)}")
        safe_print(f"DEBUG persist_run: Included screening IDs: {len(included_screening_ids)}")

        # Check which excluded records have metadata in all_records_data
        excluded_with_metadata = 0
        excluded_missing_metadata = 0
        for ext_id in excluded_screening_ids:
            if ext_id in all_records_data:
                excluded_with_metadata += 1
                title = _get_attr(all_records_data[ext_id], "title", "NO_TITLE")[:50]
                safe_print(f"DEBUG persist_run: EXCLUDED record HAS metadata: id='{ext_id}', title='{title}...'")
            else:
                excluded_missing_metadata += 1
                safe_print(f"DEBUG persist_run: EXCLUDED record MISSING metadata: id='{ext_id}'")

        safe_print(f"DEBUG persist_run: Excluded records with metadata: {excluded_with_metadata}")
        safe_print(f"DEBUG persist_run: Excluded records missing metadata: {excluded_missing_metadata}")

        # ENHANCED FALLBACK for missing records: If we have records missing metadata,
        # try to create better placeholders based on external ID patterns
        missing_count = 0
        for ext_id in screening_ids:
            if ext_id not in all_records_data:
                # Enhanced placeholder creation with better title extraction
                better_title = _extract_title_from_id(ext_id)
                all_records_data[ext_id] = {
                    "record_id": ext_id,
                    "title": better_title,
                    "source": _extract_source_from_id(ext_id)
                }
                missing_count += 1
                is_excluded = ext_id in excluded_screening_ids
                safe_print(f"DEBUG Created enhanced placeholder for missing record: {ext_id} -> '{better_title}' (excluded: {is_excluded})")

        safe_print(f"DEBUG Final record count: {len(all_records_data)} ({missing_count} placeholders)")

        # Save all records to database
        for ext_id, record in all_records_data.items():
            title = _get_attr(record, "title", "") or ""
            safe_print(f"DEBUG Saving record: id='{ext_id}', title='{title[:50]}...'")

            db_id = f"{run.id}:{ext_id}"
            s.add(
                Record(
                    id=db_id,
                    run_id=run.id,
                    title=title,
                    abstract=_get_attr(record, "abstract"),
                    authors=_get_attr(record, "authors"),
                    year=_get_attr(record, "year"),
                    doi=_get_attr(record, "doi"),
                    url=_get_attr(record, "url"),
                    source=_get_attr(record, "source", "") or "",
                    publication_type=_get_attr(record, "publication_type"),

                    # Extended metadata fields
                    journal=_get_attr(record, "journal"),
                    conference=_get_attr(record, "conference"),
                    publisher=_get_attr(record, "publisher"),
                    volume=_get_attr(record, "volume"),
                    issue=_get_attr(record, "issue"),
                    pages=_get_attr(record, "pages"),

                    # Language and location
                    language=_get_attr(record, "language"),
                    country=_get_attr(record, "country"),

                    # Additional identifiers
                    pmid=_get_attr(record, "pmid"),
                    arxiv_id=_get_attr(record, "arxiv_id"),
                    issn=_get_attr(record, "issn"),
                    isbn=_get_attr(record, "isbn"),

                    # Subject classification
                    subjects=_get_attr(record, "subjects"),
                    mesh_terms=_get_attr(record, "mesh_terms"),

                    # Full-text availability
                    pdf_url=_get_attr(record, "pdf_url"),
                    fulltext_url=_get_attr(record, "fulltext_url"),
                    open_access=_get_attr(record, "open_access"),

                    # Citation information
                    cited_by_count=_get_attr(record, "cited_by_count"),
                    reference_count=_get_attr(record, "reference_count"),
                )
            )

        # Save screening decisions - all records should already exist
        for i, screening in enumerate(screenings):
            ext_id = _get_attr(screening, "record_id", "") or ""
            decision = _get_attr(screening, "decision", "")
            reason = _get_attr(screening, "reason", "")

            if not ext_id:
                safe_print(f"DEBUG Skipping screening {i} - no record_id")
                continue

            db_rec_id = f"{run.id}:{ext_id}"
            safe_print(f"DEBUG Saving screening[{i}]: id='{ext_id}', decision='{decision}'")

            s.add(
                Screening(
                    run_id=run.id,
                    record_id=db_rec_id,
                    decision=decision,
                    reason=reason,
                )
            )

        # Appraisals
        for a in state.get("appraisals", []) or []:
            ext_id = _get_attr(a, "record_id", "")
            db_rec_id = f"{run.id}:{ext_id}"
            rating = _get_attr(a, "rating", "")
            scores = _get_attr(a, "scores", {}) or {}
            rationale = _get_attr(a, "rationale", "")
            citations = _get_attr(a, "citations", []) or []
            # Extract numeric score_final if present, otherwise compute from component scores
            score_final = None
            try:
                if isinstance(scores, dict):
                    if "final" in scores and scores.get("final") is not None:
                        score_final = float(scores.get("final"))
                    else:
                        # Attempt to compute from recency/design/bias if available
                        rec = float(scores.get("recency")) if scores.get("recency") is not None else None
                        des = float(scores.get("design")) if scores.get("design") is not None else None
                        bia = float(scores.get("bias")) if scores.get("bias") is not None else None
                        if rec is not None and des is not None and bia is not None:
                            try:
                                from app.rubric import Rubric
                                rb = Rubric.load("rubric.yaml")
                                w = rb.weights
                                score_final = rec*w["recency"] + des*w["design"] + bia*w["bias"]
                            except Exception:
                                score_final = None
            except Exception:
                score_final = None

            s.add(
                Appraisal(
                    run_id=run.id,
                    record_id=db_rec_id,
                    rating=rating,
                    scores_json=json.dumps(scores, ensure_ascii=False),
                    rationale=rationale,
                    citations_json=json.dumps(citations, ensure_ascii=False),
                    score_final=score_final,
                )
            )

        multi_method_results = state.get("multi_method_results") or {}
        if multi_method_results:
            safe_print(f"DEBUG persist_run: Persisting multi-method appraisals for {len(multi_method_results)} records")

            AppraisalMethodology.__table__.create(bind=s.bind, checkfirst=True)
            MultiMethodAppraisal.__table__.create(bind=s.bind, checkfirst=True)

            existing_methodologies = {m.method_type.value: m for m in s.query(AppraisalMethodology).all()}
            if not existing_methodologies:
                safe_print("DEBUG persist_run: No appraisal methodologies found; creating defaults")
                defaults = create_default_methodologies()
                for methodology in defaults:
                    s.add(methodology)
                s.flush()
                existing_methodologies = {m.method_type.value: m for m in s.query(AppraisalMethodology).all()}

            s.query(MultiMethodAppraisal).filter(MultiMethodAppraisal.run_id == run.id).delete(synchronize_session=False)

            for ext_id, result_bundle in multi_method_results.items():
                db_rec_id = f"{run.id}:{ext_id}"
                if s.get(Record, db_rec_id) is None:
                    safe_print(f"DEBUG persist_run: Skipping multi-method persistence for unknown record '{ext_id}'")
                    continue

                methodology_entries = result_bundle.get("methodology_results", {})
                for method_name, result_data in methodology_entries.items():
                    method_type_value = result_data.get("methodology_type")
                    if not method_type_value:
                        continue

                    methodology = existing_methodologies.get(method_type_value)
                    if not methodology:
                        try:
                            method_type_enum = AppraisalMethodType(method_type_value)
                        except ValueError:
                            method_type_enum = AppraisalMethodType.CUSTOM
                        methodology = AppraisalMethodology(
                            name=result_data.get("methodology_name", method_type_value.replace('_', ' ').title()),
                            method_type=method_type_enum,
                            description=result_data.get("methodology_name", method_type_value),
                            requires_full_text=bool(result_data.get("used_full_text", False))
                        )
                        methodology.criteria = {}
                        methodology.scoring_config = {}
                        s.add(methodology)
                        s.flush()
                        existing_methodologies[method_type_value] = methodology

                    mma = MultiMethodAppraisal(
                        run_id=run.id,
                        record_id=db_rec_id,
                        methodology_id=methodology.id,
                        overall_score=float(result_data.get("overall_score", 0.0)),
                        rating=str(result_data.get("rating", "")),
                        rationale=result_data.get("rationale"),
                        confidence=float(result_data.get("confidence", 0.0)),
                        used_full_text=bool(result_data.get("used_full_text", False)),
                        assessment_time=float(result_data.get("assessment_time", 0.0))
                    )
                    mma.scores = result_data.get("detailed_scores", {})
                    mma.sections_analyzed = result_data.get("sections_analyzed") or []
                    s.add(mma)

        # PRISMA counts
        pc = state.get("prisma")
        if pc:
            # pc may be a Pydantic model or a dict
            identified = _get_attr(pc, "identified", 0)
            deduped = _get_attr(pc, "deduped", 0)
            screened = _get_attr(pc, "screened", 0)
            excluded = _get_attr(pc, "excluded", 0)
            eligible = _get_attr(pc, "eligible", 0)
            included = _get_attr(pc, "included", 0)

            s.add(
                PrismaCounts(
                    run_id=run.id,
                    identified=identified,
                    deduped=deduped,
                    screened=screened,
                    excluded=excluded,
                    eligible=eligible,
                    included=included,
                )
            )

        s.commit()
        safe_print(f"DEBUG persist_run: Successfully persisted run {run.id} with {len(all_records_data)} total records")
        return run.id
