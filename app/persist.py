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
                    year=_get_attr(r, "year"),
                    doi=_get_attr(r, "doi"),
                    url=_get_attr(r, "url"),
                    source=_get_attr(r, "source", "") or "",
                )
            )

        # Screenings (persist reasons for PRISMA)
        for scr in state.get("screenings", []) or []:
            ext_id = _get_attr(scr, "record_id", "")
            db_rec_id = id_map.get(ext_id, f"{run.id}:{ext_id}")
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

            s.add(
                Appraisal(
                    run_id=run.id,
                    record_id=db_rec_id,
                    rating=rating,
                    scores_json=json.dumps(scores, ensure_ascii=False),
                    rationale=rationale,
                    citations_json=json.dumps(citations, ensure_ascii=False),
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
