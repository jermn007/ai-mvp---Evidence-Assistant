from __future__ import annotations
import json
from typing import Dict, Any
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

def _get_attr(obj, key, default=None):
    """Read from a Pydantic model OR a plain dict."""
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default

def persist_run(state: Dict[str, Any]) -> str:
    init_db()
    run_id = state.get("run_id") or str(uuid4())

    with get_session() as s:
        # If a run with this ID already exists (e.g., reused state), mint a new one
        if s.get(SearchRun, run_id) is not None:
            run_id = str(uuid4())

        id_map: Dict[str, str] = {}

        # Create the run row with the final run_id
        run = SearchRun(id=run_id, query=state.get("query", ""))
        s.add(run)
        s.flush()

        # Records - save ALL records (included AND excluded) with full metadata
        # First, collect all record data from both included records and screenings
        all_records = {}
        
        # Add included records (these have full metadata)
        for r in state.get("records", []) or []:
            ext_id = _get_attr(r, "record_id", "") or ""
            all_records[ext_id] = r
        
        # Check if we need to retrieve excluded records metadata from workflow state
        # The workflow may store original records before screening in a different key
        original_records = state.get("original_records", []) or state.get("harvested_records", [])
        if not original_records:
            # Look for records in the nodes before screening filtered them out
            # This is a fallback - the workflow should ideally preserve original records
            pass
        
        for r in original_records:
            ext_id = _get_attr(r, "record_id", "") or ""
            if ext_id not in all_records:  # Don't override included records
                all_records[ext_id] = r
        
        # Now save all records with full metadata
        for ext_id, r in all_records.items():
            db_id = f"{run.id}:{ext_id}"
            id_map[ext_id] = db_id

            s.add(
                Record(
                    id=db_id,
                    run_id=run.id,
                    title=_get_attr(r, "title", "") or "",
                    abstract=_get_attr(r, "abstract"),
                    authors=_get_attr(r, "authors"),
                    year=_get_attr(r, "year"),
                    doi=_get_attr(r, "doi"),
                    url=_get_attr(r, "url"),
                    source=_get_attr(r, "source", "") or "",
                    publication_type=_get_attr(r, "publication_type"),
                    
                    # Extended metadata fields
                    journal=_get_attr(r, "journal"),
                    conference=_get_attr(r, "conference"),
                    publisher=_get_attr(r, "publisher"),
                    volume=_get_attr(r, "volume"),
                    issue=_get_attr(r, "issue"),
                    pages=_get_attr(r, "pages"),
                    
                    # Language and location
                    language=_get_attr(r, "language"),
                    country=_get_attr(r, "country"),
                    
                    # Additional identifiers
                    pmid=_get_attr(r, "pmid"),
                    arxiv_id=_get_attr(r, "arxiv_id"),
                    issn=_get_attr(r, "issn"),
                    isbn=_get_attr(r, "isbn"),
                    
                    # Subject classification
                    subjects=_get_attr(r, "subjects"),
                    mesh_terms=_get_attr(r, "mesh_terms"),
                    
                    # Full-text availability
                    pdf_url=_get_attr(r, "pdf_url"),
                    fulltext_url=_get_attr(r, "fulltext_url"),
                    open_access=_get_attr(r, "open_access"),
                    
                    # Citation information
                    cited_by_count=_get_attr(r, "cited_by_count"),
                    reference_count=_get_attr(r, "reference_count"),
                )
            )

        # Screenings - now all should have corresponding Record entries with full data
        for scr in state.get("screenings", []) or []:
            ext_id = _get_attr(scr, "record_id", "") or ""
            db_rec_id = id_map.get(ext_id)
            
            if not db_rec_id:
                # This should not happen now, but keep as fallback
                db_rec_id = f"{run.id}:{ext_id}"
                # Create minimal placeholder only as absolute fallback
                s.add(
                    Record(
                        id=db_rec_id,
                        run_id=run.id,
                        title=f"Record {ext_id}",  # Better than empty string
                        abstract=None,
                        authors=None,
                        year=None,
                        doi=None,
                        url=None,
                        source="Unknown",
                        publication_type=None,
                    )
                )
                
            s.add(
                Screening(
                    run_id=run.id,
                    record_id=db_rec_id,
                    decision=_get_attr(scr, "decision", ""),
                    reason=_get_attr(scr, "reason", ""),
                )
            )

        # Appraisals
        for a in state.get("appraisals", []) or []:
            ext_id = _get_attr(a, "record_id", "")
            db_rec_id = id_map.get(ext_id, f"{run.id}:{ext_id}")
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
        return run.id
