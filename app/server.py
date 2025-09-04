# app/server.py
from __future__ import annotations

import os
from uuid import uuid4
import asyncio
import io
import csv
from collections import Counter, defaultdict
from typing import Sequence, List, Optional
import importlib

from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, or_, func, cast, case
from sqlalchemy.types import Float as SA_Float

# Load .env early so DATABASE_URL etc. are visible to build.py
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.sources import (
    pubmed_search_async,
    crossref_search_async,
    arxiv_search_async,
    eric_search_async,
    s2_search_async,
    scholar_serpapi_async,
)
from app.graph.build import get_graph, CHECKPOINTER
from app.persist import persist_run

# PRESS contract / planner
from app.press_contract import LICO, DatabaseSpec, PressPlanResponse
from app.press import plan_press_from_lico
from app.press_hits import fill_hits_for_pubmed

# --- DB compatibility layer (works with async or sync app.db) -----------------
_db = importlib.import_module("app.db")

# Models (must exist)
Record = getattr(_db, "Record")
Appraisal = getattr(_db, "Appraisal")

def _has(name: str) -> bool:
    return hasattr(_db, name) and callable(getattr(_db, name))

async def _select_stmt(stmt):
    if _has("async_session"):
        async with _db.async_session() as s:
            res = await s.execute(stmt)
            return res.scalars().all()
    if _has("AsyncSessionLocal"):
        async with _db.AsyncSessionLocal() as s:
            res = await s.execute(stmt)
            return res.scalars().all()
    if _has("SessionLocal"):
        def _run():
            with _db.SessionLocal() as s:
                res = s.execute(stmt)
                return res.scalars().all()
        return await asyncio.to_thread(_run)
    if _has("session"):
        def _run():
            with _db.session() as s:
                res = s.execute(stmt)
                return res.scalars().all()
        return await asyncio.to_thread(_run)
    raise RuntimeError("No usable session factory in app.db.")

async def _count_stmt(stmt):
    subq = stmt.subquery()
    count_q = select(func.count()).select_from(subq)
    if _has("async_session"):
        async with _db.async_session() as s:
            res = await s.execute(count_q)
            return int(res.scalar() or 0)
    if _has("AsyncSessionLocal"):
        async with _db.AsyncSessionLocal() as s:
            res = await s.execute(count_q)
            return int(res.scalar() or 0)
    if _has("SessionLocal"):
        def _run():
            with _db.SessionLocal() as s:
                res = s.execute(count_q)
                return int(res.scalar() or 0)
        return await asyncio.to_thread(_run)
    if _has("session"):
        def _run():
            with _db.session() as s:
                res = s.execute(count_q)
                return int(res.scalar() or 0)
        return await asyncio.to_thread(_run)
    raise RuntimeError("No usable session factory in app.db.")
# -----------------------------------------------------------------------------


app = FastAPI(title="Evidence Assistant (MVP)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GRAPH = get_graph()


class RunRequest(BaseModel):
    query: str
    thread_id: str | None = None


@app.get("/health")
def health():
    return {"ok": True, "env": bool(os.getenv("OPENAI_API_KEY"))}


@app.get("/health/checkpointer")
def health_checkpointer():
    try:
        from langgraph.checkpoint.memory import MemorySaver
        kind = "memory" if isinstance(CHECKPOINTER, MemorySaver) else "postgres"
    except Exception:
        kind = CHECKPOINTER.__class__.__name__
    return {"checkpointer": kind}


@app.post("/run")
def run(req: RunRequest):
    try:
        tid = req.thread_id or str(uuid4())
        final = GRAPH.invoke(
            {"query": req.query},
            config={"configurable": {"thread_id": tid}},
        )
        run_id = persist_run(final)
        prisma = final["prisma"].model_dump() if hasattr(final.get("prisma"), "model_dump") else final.get("prisma", {})
        ratings = [a.rating for a in final.get("appraisals", [])]

        return {
            "thread_id": tid,
            "run_id": run_id,
            "prisma": prisma,
            "n_appraised": len(ratings),
            "ratings": ratings,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"run failed: {type(e).__name__}: {e}")


@app.get("/sources/test")
async def sources_test(q: str = "active learning in higher education", max_n: int = 5):
    year_min = 2019
    try:
        batches = await asyncio.gather(
            pubmed_search_async(q, max_n=max_n),
            crossref_search_async(q, max_n=max_n, mailto=os.getenv("CROSSREF_MAILTO")),
            arxiv_search_async(q, max_n=max_n),
            eric_search_async(q, max_n=max_n),
            s2_search_async(q, max_n=max_n),
            scholar_serpapi_async(q, max_n=max_n, year_min=year_min),
            return_exceptions=True,
        )
        names = ["PubMed", "Crossref", "arXiv", "ERIC", "SemanticScholar", "Scholar"]
        out = {}
        for name, batch in zip(names, batches):
            if isinstance(batch, Exception):
                out[name] = {"count": 0, "error": str(type(batch).__name__)}
            else:
                out[name] = {"count": len(batch)}
        return {"query": q, "max_n": max_n, "year_min": year_min, "sources": out}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ======================= Export helpers =======================

COLS_RECORD = ["id", "run_id", "title", "abstract", "year", "doi", "url", "source", "created_at"]
COLS_APPRAISAL = ["id", "run_id", "record_id", "rating", "rationale", "scores_json", "citations_json", "score_final", "created_at"]

def _pick_columns(rows: Sequence[object], preferred: list[str]) -> list[str]:
    if not rows:
        return preferred
    row = rows[0]
    got = [c for c in preferred if hasattr(row, c)]
    if not got:
        keys = [k for k in getattr(row, "__dict__", {}).keys() if not k.startswith("_")]
        return keys
    return got

def _rows_to_json(rows: Sequence[object], cols: list[str]) -> list[dict]:
    return [{c: getattr(r, c, None) for c in cols} for r in rows]

def _rows_to_csv(rows: Sequence[object], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([getattr(r, c, None) for c in cols])
    return buf.getvalue()

def _numeric_like(col):
    pattern = r'^\s*[+-]?((\d+(\.\d+)?)|(\.\d+))\s*$'
    return case(
        (col.op("~")(pattern), cast(col, SA_Float)),
        else_=None,
    )

def _label_rank_expr(col, order: list[str]):
    """
    Map labels to ranks via CASE; unknown -> -1.
    """
    whens = []
    for idx, val in enumerate(order):
        whens.append((col == val, idx))
    return case(*whens, else_=-1)


# ======================= Basic exports =======================

from sqlalchemy import select as SAselect

@app.get("/runs/{run_id}/records.json")
async def export_records_json(run_id: str):
    stmt = SAselect(Record).where(Record.run_id == run_id)
    rows = await _select_stmt(stmt)
    cols = _pick_columns(rows, COLS_RECORD)
    return _rows_to_json(rows, cols)

@app.get("/runs/{run_id}/records.csv")
async def export_records_csv(run_id: str):
    stmt = SAselect(Record).where(Record.run_id == run_id)
    rows = await _select_stmt(stmt)
    cols = _pick_columns(rows, COLS_RECORD)
    csv_body = _rows_to_csv(rows, cols)
    return Response(content=csv_body, media_type="text/csv")

@app.get("/runs/{run_id}/appraisals.json")
async def export_appraisals_json(run_id: str):
    stmt = SAselect(Appraisal).where(Appraisal.run_id == run_id)
    rows = await _select_stmt(stmt)
    cols = _pick_columns(rows, COLS_APPRAISAL)
    return _rows_to_json(rows, cols)

@app.get("/runs/{run_id}/appraisals.csv")
async def export_appraisals_csv(run_id: str):
    stmt = SAselect(Appraisal).where(Appraisal.run_id == run_id)
    rows = await _select_stmt(stmt)
    cols = _pick_columns(rows, COLS_APPRAISAL)
    csv_body = _rows_to_csv(rows, cols)
    return Response(content=csv_body, media_type="text/csv")

@app.get("/runs/{run_id}/summary.json")
async def export_run_summary(run_id: str):
    rec_stmt = SAselect(Record).where(Record.run_id == run_id)
    app_stmt = SAselect(Appraisal).where(Appraisal.run_id == run_id)
    records, appraisals = await asyncio.gather(_select_stmt(rec_stmt), _select_stmt(app_stmt))

    by_source = Counter(getattr(r, "source", None) for r in records)
    if None in by_source:
        by_source["unknown"] += by_source.pop(None)

    # Label histogram
    labels = [getattr(a, "rating", None) for a in appraisals]
    label_hist = Counter([x for x in labels if x is not None])

    # Numeric stats (score_final preferred; fallback to numeric-looking rating)
    def to_float(x):
        try:
            return float(x)
        except Exception:
            return None
    nums = [getattr(a, "score_final", None) for a in appraisals]
    nums = [n for n in nums if isinstance(n, (int, float))]
    if not nums:
        # fallback: try parsing rating strings
        nums = [to_float(getattr(a, "rating", None)) for a in appraisals]
        nums = [n for n in nums if n is not None]
    numeric_summary = None
    if nums:
        numeric_summary = {"count": len(nums), "min": min(nums), "max": max(nums), "avg": sum(nums)/len(nums)}

    return {
        "run_id": run_id,
        "records_total": len(records),
        "records_by_source": dict(by_source),
        "appraisals_total": len(appraisals),
        "ratings_histogram": dict(label_hist),
        "numeric_summary": numeric_summary,
    }


# ======================= Paged & filtered appraisals =======================

_ORDERABLE_APPRAISAL = ("created_at", "rating", "score_final", "id")

@app.get("/runs/{run_id}/appraisals.page.json")
async def export_appraisals_page(
    run_id: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0, le=100000),
    # numeric filters (prefer score_final)
    score_min: float | None = None,
    score_max: float | None = None,
    rating_min: float | None = None,   # legacy numeric rating support
    rating_max: float | None = None,   # (added) legacy numeric rating upper bound
    # label filters
    label_in: str | None = None,
    label_min: str | None = None,
    label_order: str | None = None,  # CSV, default "Red,Amber,Green"
    # sorting
    order_by: str = Query("created_at"),
    order_dir: str = Query("desc"),
):
    stmt = SAselect(Appraisal).where(Appraisal.run_id == run_id)

    # --- parse label order & helpers
    order_labels = [x.strip() for x in (label_order or "Red,Amber,Green").split(",") if x.strip()]
    label_rank = _label_rank_expr(Appraisal.rating, order_labels)

    # --- label_in: categorical whitelist
    if label_in:
        labels = [x.strip() for x in label_in.split(",") if x.strip()]
        if labels:
            stmt = stmt.where(Appraisal.rating.in_(labels))

    # --- label_min: include labels >= threshold on the defined scale
    if label_min:
        try:
            threshold = order_labels.index(label_min)
            stmt = stmt.where(label_rank >= threshold)
        except ValueError:
            # unknown label_min; no-op
            pass

    # --- numeric filters: prefer score_final if column exists/populated
    score_col = getattr(Appraisal, "score_final", None)
    if score_col is not None:
        if score_min is not None:
            stmt = stmt.where(score_col >= float(score_min))
        if score_max is not None:
            stmt = stmt.where(score_col <= float(score_max))
    else:
        # fallback to numeric-looking rating
        num_rating = _numeric_like(Appraisal.rating)
        if rating_min is not None:
            stmt = stmt.where(num_rating >= float(rating_min))
        if rating_max is not None:
            stmt = stmt.where(num_rating <= float(rating_max))

    # --- ordering
    if order_by not in _ORDERABLE_APPRAISAL or not hasattr(Appraisal, order_by):
        order_by = "created_at" if hasattr(Appraisal, "created_at") else "id"

    if order_by == "rating":
        # If user provided label order, sort by the label rank; otherwise try numeric-looking rating
        order_col = label_rank if label_order or label_min or label_in else _numeric_like(Appraisal.rating)
    else:
        order_col = getattr(Appraisal, order_by)

    # For rating when neither label nor numeric applies, default to text order
    if order_by == "rating" and order_col is None:
        order_col = Appraisal.rating

    # Final order direction
    if order_dir.lower() == "desc":
        try:
            order_col = order_col.desc().nulls_last()
        except Exception:
            order_col = order_col.desc()
    else:
        try:
            order_col = order_col.asc().nulls_last()
        except Exception:
            order_col = order_col.asc()

    stmt = stmt.order_by(order_col)

    # Count & page
    total = await _count_stmt(stmt)
    stmt = stmt.offset(offset).limit(limit)
    rows = await _select_stmt(stmt)
    cols = _pick_columns(rows, COLS_APPRAISAL)
    return {
        "run_id": run_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": _rows_to_json(rows, cols),
    }


# ======================= PRESS planner endpoints =======================

class PressPlanBody(BaseModel):
    lico: LICO
    databases: Optional[List[DatabaseSpec]] = None

@app.post("/press/plan", response_model=PressPlanResponse)
async def make_press_plan(body: PressPlanBody):
    """Return a PRESS-compatible, LICO-driven strategy (numbered boolean lines + self-check)."""
    return plan_press_from_lico(body.lico, body.databases)

async def _get_run_query(run_id: str) -> Optional[str]:
    """Try to load the original free-text query for a run from common model names."""
    candidate_models = ["SearchRun", "Run", "RunModel", "SearchJob"]
    for name in candidate_models:
        if hasattr(_db, name):
            Model = getattr(_db, name)
            try:
                rows = await _select_stmt(SAselect(Model).where(Model.id == run_id))
                if rows:
                    row = rows[0]
                    for attr in ("query", "q", "question", "prompt"):
                        if hasattr(row, attr):
                            val = getattr(row, attr)
                            if isinstance(val, str) and val.strip():
                                return val.strip()
            except Exception:
                continue
    return None

@app.get("/runs/{run_id}/press.plan.json", response_model=PressPlanResponse)
async def press_plan_for_run(
    run_id: str,
    learner: Optional[str] = None,
    intervention: Optional[str] = None,
    context: Optional[str] = None,
    outcome: Optional[str] = None,
    db_name: Optional[str] = Query(None, description="e.g., MEDLINE"),
    interface: Optional[str] = Query(None, description="e.g., PubMed"),
):
    """
    Build a PRESS-compatible plan for an existing run.
    If LICO parts aren't provided, we will:
      - try to fetch the run's original free-text query and use it as 'intervention'
      - use generic defaults for other facets (LICO) so output is still useful
    """
    q = await _get_run_query(run_id)
    if not any([learner, intervention, context, outcome]) and not q:
        raise HTTPException(status_code=404, detail="Could not resolve run query; provide LICO via query params or use POST /press/plan.")

    lico = LICO(
        learner      = learner or "health professions learners or students",
        intervention = intervention or (q or "education intervention"),
        context      = context or "",
        outcome      = outcome or "knowledge, skills, attitudes, or behavior"
    )

    databases = None
    if db_name:
        databases = [DatabaseSpec(name=db_name, interface=interface or "PubMed")]

    return plan_press_from_lico(lico, databases)

# --- With counts (PubMed) -----------------------------------------------------

@app.post("/press/plan/hits", response_model=PressPlanResponse)
async def make_press_plan_with_hits(body: PressPlanBody):
    plan = plan_press_from_lico(body.lico, body.databases)
    # fill for MEDLINE/PubMed only
    if "MEDLINE" in plan.strategies:
        plan.strategies["MEDLINE"] = await fill_hits_for_pubmed(plan.strategies["MEDLINE"])
    return plan

@app.get("/runs/{run_id}/press.plan.hits.json", response_model=PressPlanResponse)
async def press_plan_for_run_with_hits(
    run_id: str,
    learner: Optional[str] = None,
    intervention: Optional[str] = None,
    context: Optional[str] = None,
    outcome: Optional[str] = None,
    db_name: Optional[str] = Query("MEDLINE", description="Currently supports MEDLINE/PubMed"),
    interface: Optional[str] = Query("PubMed", description="Currently supports PubMed"),
):
    # Reuse GET plan builder
    base = await press_plan_for_run(run_id, learner, intervention, context, outcome, db_name, interface)
    if db_name == "MEDLINE" and interface.lower() == "pubmed":
        base.strategies["MEDLINE"] = await fill_hits_for_pubmed(base.strategies["MEDLINE"])
    return base
