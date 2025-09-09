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
        s.add(run); s.flush()

    with get_session() as s:
        # Run row
        run = SearchRun(id=run_id, query=state.get("query", ""))
        s.add(run)
        s.flush()

        # Records
        for r in state.get("records", []) or []:
            ext_id = _get_attr(r, "record_id", "") or ""
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
                )
            )

        # Screenings (persist reasons for PRISMA)
        # Ensure every screened item has a corresponding Record row for FK integrity.
        # For excluded items (not in id_map), insert a minimal placeholder Record.
        minimal_created: Dict[str, bool] = {}
        for scr in state.get("screenings", []) or []:
            ext_id = _get_attr(scr, "record_id", "") or ""
            db_rec_id = id_map.get(ext_id)
            if not db_rec_id:
                db_rec_id = f"{run.id}:{ext_id}"
                if not minimal_created.get(db_rec_id):
                    # Insert minimal placeholder to satisfy FK; fields kept empty/nullable
                    s.add(
                        Record(
                            id=db_rec_id,
                            run_id=run.id,
                            title="",
                            abstract=None,
                            authors=None,
                            year=None,
                            doi=None,
                            url=None,
                            source="",
                            publication_type=None,
                        )
                    )
                    minimal_created[db_rec_id] = True
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
