# app/server.py
from __future__ import annotations

import os
import logging
# DEBUG: Force reload to pick up persist.py changes
from uuid import uuid4
import asyncio
import io
import csv
import re
from collections import Counter, defaultdict
from typing import Sequence, List, Optional, Dict, Any
import importlib
from types import SimpleNamespace as _NS

from fastapi import FastAPI, HTTPException, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import select, or_, func, cast, case
from sqlalchemy.types import Float as SA_Float
from app.utils.strings import strip_or_empty, norm_lower

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
from app.models import PressPlan

# PRESS contract / planner types + hits helper
from app.press_contract import LICO, DatabaseSpec, PressPlanResponse, PressStrategy, StrategyLine
from app.press_hits import fill_hits_for_pubmed, _expand_lines_to_queries
from app.ai_service import get_ai_service, LICOEnhancement, PressStrategyAnalysis, StudyRelevanceAssessment
from app.research_synthesizer import (
    extract_study_findings,
    synthesize_research,
    ResearchSynthesis,
    extract_study_findings_sync,
    synthesize_research_sync,
)
from app.middleware import setup_middleware

# --- DB compatibility layer (works with async or sync app.db) -----------------
_db = importlib.import_module("app.db")
# Ensure DB schema is initialized and compatible with latest models
try:
    if hasattr(_db, "init_db"):
        _db.init_db()
except Exception:
    pass

# Models (must exist)
Record = getattr(_db, "Record")
Appraisal = getattr(_db, "Appraisal")
Screening = getattr(_db, "Screening", None)
PrismaCounts = getattr(_db, "PrismaCounts", None)

FULLTEXT_USAGE_CACHE: Dict[str, Dict[str, bool]] = {}


def _annotate_full_text_usage(run_id: str, rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach cached full-text usage flags to exported record rows."""
    usage = FULLTEXT_USAGE_CACHE.get(run_id, {})
    annotated: List[Dict[str, Any]] = []
    for row in rows:
        mapping = dict(row)
        record_id = mapping.get("record_id")
        mapping["full_text_used"] = bool(usage.get(record_id, False)) if record_id else False
        annotated.append(mapping)
    return annotated

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

async def _select_mappings(stmt):
    """Execute a select and return list of mapping dicts (column aliases -> values)."""
    if _has("async_session"):
        async with _db.async_session() as s:
            res = await s.execute(stmt)
            return res.mappings().all()
    if _has("AsyncSessionLocal"):
        async with _db.AsyncSessionLocal() as s:
            res = await s.execute(stmt)
            return res.mappings().all()
    if _has("SessionLocal"):
        def _run():
            with _db.SessionLocal() as s:
                res = s.execute(stmt)
                return res.mappings().all()
        return await asyncio.to_thread(_run)
    if _has("session"):
        def _run():
            with _db.session() as s:
                res = s.execute(stmt)
                return res.mappings().all()
        return await asyncio.to_thread(_run)
    raise RuntimeError("No usable session factory in app.db.")


logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="Evidence Assistant (AI-Powered Literature Review)",
    summary="Automate systematic literature reviews with 5-step PRESS workflow",
    description="""# Evidence Assistant API

A comprehensive AI-powered research automation platform for systematic literature reviews.

## Features
- **PRESS Planning**: Structured search strategy development with LICO framework
- **Multi-Database Harvesting**: Search 6 academic databases simultaneously
- **Intelligent Deduplication**: 96% threshold fuzzy matching with screening
- **AI Quality Appraisal**: Rubric-based scoring with 8 weighted criteria
- **PRISMA Reporting**: Automated flow statistics and export capabilities

## Workflow
1. **Plan** → Generate PRESS search strategy from research question
2. **Harvest** → Search PubMed, Crossref, arXiv, ERIC, Semantic Scholar, Google Scholar
3. **Dedupe & Screen** → Remove duplicates and apply inclusion/exclusion criteria
4. **Appraise** → Quality assessment with Red/Amber/Green ratings
5. **Report** → Generate PRISMA flow diagrams and export results

## Research Domains
Supports clinical, education, and general research with domain-specific templates.
""",
    version="1.0.0",
    contact={
        "name": "Evidence Assistant Team",
        "email": "support@evidence-assistant.ai"
    },
    license_info={
        "name": "MIT",
        "identifier": "MIT"
    },
    openapi_tags=[
        {
            "name": "health",
            "description": "System health and status monitoring endpoints"
        },
        {
            "name": "workflows",
            "description": "Core literature review workflow execution. Execute complete 5-step research pipelines."
        },
        {
            "name": "press",
            "description": "PRESS (Peer Review of Electronic Search Strategies) planning and query generation. Create structured search strategies using LICO framework."
        },
        {
            "name": "sources",
            "description": "Academic database connectivity and testing. Verify connections to PubMed, Crossref, arXiv, ERIC, Semantic Scholar, and Google Scholar."
        },
        {
            "name": "export",
            "description": "Data export and reporting. Download results in JSON, CSV formats with PRISMA statistics."
        },
        {
            "name": "ai",
            "description": "AI-powered research assistance. Enhanced LICO analysis, strategy optimization, and study relevance assessment."
        }
    ]
)

# Configure comprehensive middleware (logging, monitoring, security, rate limiting)
setup_middleware(app, enable_rate_limiting=True)

# Note: Request logging now handled by comprehensive middleware in setup_middleware()

GRAPH = get_graph()


class RunRequest(BaseModel):
    """Request model for executing a complete literature review workflow."""
    query: str | None = None
    lico: LICO | None = None
    years: str | None = None                 # e.g., "2019-"
    sources: List[str] | None = None         # e.g., ["PubMed","ERIC",...]
    thread_id: str | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "active learning strategies in medical education",
                    "years": "2019-",
                    "sources": ["PubMed", "ERIC", "Crossref"]
                },
                {
                    "lico": {
                        "learner": "medical students",
                        "intervention": "simulation-based learning",
                        "context": "clinical skills training",
                        "outcome": "competency assessment scores"
                    },
                    "years": "2020-",
                    "sources": ["PubMed", "ERIC", "SemanticScholar"]
                }
            ]
        }
    }


@app.get(
    "/health",
    tags=["health"],
    summary="Check system health",
    description="Verify system status and environment configuration",
    response_description="System health status with environment checks"
)
def health():
    """Health check endpoint for monitoring system status and configuration."""
    return {"ok": True, "env": bool(os.getenv("OPENAI_API_KEY"))}


@app.get(
    "/health/checkpointer",
    tags=["health"],
    summary="Check workflow persistence status",
    description="Verify LangGraph checkpointer configuration for workflow state persistence",
    response_description="Checkpointer type and status information"
)
def health_checkpointer():
    """Check the type and status of the workflow state persistence system."""
    try:
        from langgraph.checkpoint.memory import MemorySaver
        kind = "memory" if isinstance(CHECKPOINTER, MemorySaver) else "postgres"
    except Exception:
        kind = CHECKPOINTER.__class__.__name__
    return {"checkpointer": kind}


@app.post(
    "/run",
    tags=["workflows"],
    summary="Execute complete literature review workflow",
    description="Run the full 5-step systematic literature review process: PRESS planning → harvesting → deduplication/screening → appraisal → PRISMA reporting",
    response_description="Workflow execution results with PRISMA statistics and quality ratings"
)
async def run(req: RunRequest):
    try:
        tid = req.thread_id or str(uuid4())
        # Build initial state: support either free-text query or LICO-driven query
        init_state: dict = {}

        # Decide query string to feed connectors
        if req.lico is not None:
            l = req.lico
            q_exec = " ".join([s for s in [l.learner, l.intervention, l.context, l.outcome] if s])
            init_state["query"] = q_exec

            # Construct a simple PRESS plan to carry along
            years = req.years or os.getenv("PRESS_YEAR_MIN", "2019-")
            srcs = req.sources or ["PubMed", "Crossref", "ERIC", "SemanticScholar", "GoogleScholar", "arXiv"]
            boolean = " AND ".join([f'("{s}")' for s in [l.learner, l.intervention, l.context, l.outcome] if s]) or q_exec
            init_state["press"] = PressPlan(concepts=[c for c in [l.learner, l.intervention, l.context, l.outcome] if c],
                                             boolean=boolean,
                                             sources=srcs,
                                             years=years)
        else:
            # Fallback to free-text query
            init_state["query"] = strip_or_empty(req.query)

        final = await GRAPH.ainvoke(init_state, config={"configurable": {"thread_id": tid}})
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


# ======================= Run from PRESS plan =======================

class RunWithPressBody(BaseModel):
    """Request model for executing workflow with a pre-generated PRESS plan."""
    plan: PressPlanResponse
    sources: Optional[List[str]] = None
    thread_id: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "sources": ["PubMed", "Crossref", "ERIC", "SemanticScholar"],
                    "plan": {
                        "question_lico": {
                            "learner": "healthcare students",
                            "intervention": "virtual reality training",
                            "context": "surgical skills education",
                            "outcome": "technical skill acquisition"
                        },
                        "strategies": {
                            "MEDLINE": {
                                "database": "MEDLINE",
                                "interface": "PubMed",
                                "lines": [
                                    {"n": 1, "type": "Learner", "text": "(healthcare students[tiab] OR medical students[tiab])", "hits": None},
                                    {"n": 2, "type": "Intervention", "text": "(virtual reality[tiab] OR VR training[tiab])", "hits": None},
                                    {"n": 3, "type": "Combine", "text": "1 AND 2", "hits": None}
                                ]
                            }
                        }
                    }
                }
            ]
        }
    }

def _pubmed_query_from_strategy(strat: PressStrategy | dict) -> tuple[str, Optional[str]]:
    """Return (final_query, years_from_limits_or_none) from a MEDLINE/PubMed strategy.
    Uses Combine + Limits expansion via _expand_lines_to_queries.
    """
    # Accept dict or PressStrategy
    if isinstance(strat, dict):
        ns = _strategy_dict_to_ns(strat)
    else:
        # Convert pydantic model to our NS for reuse
        ns = _NS(database=strat.database, interface=strat.interface, lines=[_NS(**ln.model_dump()) for ln in strat.lines])
    qmap = _expand_lines_to_queries(getattr(ns, "lines", []) or [])  # type: ignore[arg-type]
    lines = getattr(ns, "lines", []) or []
    # Prefer Limits line, else last Combine, else highest line number
    last_n = None
    years = None
    for ln in lines:
        if getattr(ln, "type", None) == "Limits":
            last_n = getattr(ln, "n", None)
            # Try to parse years like 2015:3000[dp]
            txt = getattr(ln, "text", "") or ""
            m = re.search(r"(19|20)\d{2}\s*:\s*(?:3000|\d{4})", txt)
            if m:
                years = f"{m.group(0)[:4]}-"
            break
    if last_n is None:
        # Look for Combine
        combines = [getattr(ln, "n", None) for ln in lines if getattr(ln, "type", None) == "Combine"]
        if combines:
            last_n = combines[-1]
    if last_n is None and lines:
        last_n = getattr(lines[-1], "n", None)
    # Safely get the final query, ensuring it's never None
    q_final = ""
    if qmap:
        if last_n and last_n in qmap:
            q_final = qmap[last_n]
        elif qmap:
            # Get the query with the highest key
            max_key = max(qmap.keys())
            q_final = qmap[max_key]
    
    # Ensure we never return None
    q_final = q_final or ""
    return q_final, years

def _genericize_query(pubmed_q: str | None) -> str:
    """Strip PubMed field tags and keep a textual boolean query suitable for general sources."""
    q = strip_or_empty(pubmed_q)
    # Remove square-bracket tags like [tiab], [Mesh], [dp], [la]
    q = re.sub(r"\[[^\]]+\]", "", q)
    # Collapse excessive parentheses and whitespace
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"\(\s*\)", "", q)
    return q.strip()

@app.post(
    "/run/press",
    tags=["workflows"],
    summary="Execute workflow with PRESS plan",
    description="Run literature review workflow using a pre-generated PRESS search strategy with optimized database queries",
    response_description="Workflow results with query details and execution metrics"
)
async def run_with_press(body: RunWithPressBody):
    try:
        logger.info(f"run_with_press: endpoint called with thread_id={getattr(body, 'thread_id', None)}")
        tid = body.thread_id or str(uuid4())
        plan = body.plan
        logger.info(f"run_with_press: processing plan with {len(plan.strategies) if hasattr(plan, 'strategies') else 'unknown'} strategies")
        # Pull MEDLINE/PubMed strategy
        strat = plan.strategies.get("MEDLINE") if isinstance(plan.strategies, dict) else None
        if strat is None:
            raise HTTPException(status_code=400, detail="Plan missing MEDLINE strategy")

        try:
            pubmed_q, years = _pubmed_query_from_strategy(strat)
            logger.info(f"run_with_press: extracted pubmed_q: {pubmed_q[:100]}...")
        except Exception as e:
            logger.error(f"run_with_press: _pubmed_query_from_strategy failed: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"run_with_press: _pubmed_query_from_strategy traceback: {traceback.format_exc()}")
            raise
            
        try:
            generic_q = _genericize_query(pubmed_q)
            logger.info(f"run_with_press: generic_q: {generic_q[:100]}...")
        except Exception as e:
            logger.error(f"run_with_press: _genericize_query failed: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"run_with_press: _genericize_query traceback: {traceback.format_exc()}")
            raise

        # Choose sources: override or sensible default
        srcs = body.sources or ["PubMed", "Crossref", "ERIC", "SemanticScholar", "GoogleScholar", "arXiv"]
        years_final = years or os.getenv("PRESS_YEAR_MIN", "2019-")

        # Build a simple PressPlan snapshot for state
        press_snapshot = PressPlan(
            concepts=[c for c in [plan.question_lico.learner, plan.question_lico.intervention, plan.question_lico.context, plan.question_lico.outcome] if c],
            boolean=pubmed_q,
            sources=srcs,
            years=years_final,
        )

        init_state = {"query": generic_q, "press": press_snapshot}
        logger.info(f"run_with_press: starting graph execution with query: {generic_q[:100]}...")
        logger.info(f"run_with_press: thread_id={tid}, sources={srcs}")
        
        try:
            final = await GRAPH.ainvoke(init_state, config={"configurable": {"thread_id": tid}})
            logger.info(f"run_with_press: graph execution completed successfully")
        except Exception as graph_error:
            logger.error(f"run_with_press: graph execution failed: {type(graph_error).__name__}: {graph_error}")
            import traceback
            logger.error(f"run_with_press: graph execution traceback: {traceback.format_exc()}")
            raise
            
        try:
            run_id = persist_run(final)
            logger.info(f"run_with_press: run persisted with id: {run_id}")
        except Exception as persist_error:
            logger.error(f"run_with_press: persist_run failed: {type(persist_error).__name__}: {persist_error}")
            import traceback
            logger.error(f"run_with_press: persist_run traceback: {traceback.format_exc()}")
            raise
        prisma = final["prisma"].model_dump() if hasattr(final.get("prisma"), "model_dump") else final.get("prisma", {})
        ratings = [a.rating for a in final.get("appraisals", [])]
        return {
            "thread_id": tid,
            "run_id": run_id,
            "prisma": prisma,
            "n_appraised": len(ratings),
            "ratings": ratings,
            "query_generic": generic_q,
            "query_pubmed": pubmed_q,
            "years": years_final,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"run_with_press failed: {type(e).__name__}: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"run_with_press failed: {type(e).__name__}: {e}")


# ======================= Derive queries from plan (no run) ===================

class PlanQueriesBody(BaseModel):
    plan: PressPlanResponse

@app.post(
    "/press/plan/queries",
    tags=["press"],
    summary="Extract queries from PRESS plan",
    description="Convert a PRESS search strategy into executable database queries (PubMed-specific and generic formats)",
    response_description="Generated queries ready for database execution"
)
def plan_queries(body: PlanQueriesBody):
    try:
        plan = body.plan
        strat = plan.strategies.get("MEDLINE") if isinstance(plan.strategies, dict) else None
        if strat is None:
            raise HTTPException(status_code=400, detail="Plan missing MEDLINE strategy")
        pubmed_q, years = _pubmed_query_from_strategy(strat)
        generic_q = _genericize_query(pubmed_q)
        return {"query_pubmed": pubmed_q, "query_generic": generic_q, "years": years}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"plan_queries failed: {type(e).__name__}: {e}")


@app.get(
    "/sources/test",
    tags=["sources"],
    summary="Test academic database connections",
    description="Verify connectivity and search functionality across all 6 supported academic databases with a test query",
    response_description="Connection status and result counts for each database"
)
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

def _mappings_to_csv(rows: Sequence[dict], cols: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for m in rows:
        w.writerow([m.get(c, None) for c in cols])
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

@app.get(
    "/runs/{run_id}/records.json",
    tags=["export"],
    summary="Export records as JSON",
    description="Download all research records from a literature review run in JSON format",
    response_description="Array of research records with metadata"
)
async def export_records_json(run_id: str):
    stmt = SAselect(Record).where(Record.run_id == run_id)
    rows = await _select_stmt(stmt)
    cols = _pick_columns(rows, COLS_RECORD)
    return _rows_to_json(rows, cols)

@app.get(
    "/runs/{run_id}/records.csv",
    tags=["export"],
    summary="Export records as CSV",
    description="Download all research records from a literature review run in CSV format for spreadsheet analysis",
    response_description="CSV file with research records"
)
async def export_records_csv(run_id: str):
    stmt = SAselect(Record).where(Record.run_id == run_id)
    rows = await _select_stmt(stmt)
    cols = _pick_columns(rows, COLS_RECORD)
    csv_body = _rows_to_csv(rows, cols)
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=records_{run_id}.csv"}
    )

@app.get(
    "/runs/{run_id}/appraisals.json",
    tags=["export"],
    summary="Export quality appraisals as JSON",
    description="Download all quality assessment results including Red/Amber/Green ratings, scores, and rationales",
    response_description="Array of quality appraisals with detailed scoring"
)
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
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=appraisals_{run_id}.csv"}
    )

# ======================= Joined export: records + appraisals ==================

JOIN_COLS = [
    "record_id", "title", "abstract", "authors", "year", "doi", "url", "source",
    "publication_type", "institution", "rating", "score_final", "rationale", "full_text_used", "run_id"
]

@app.get(
    "/runs/{run_id}/records_with_appraisals.json",
    tags=["export"],
    summary="Export joined records with quality ratings",
    description="Download research records combined with their quality appraisal results in a single JSON structure",
    response_description="Joined dataset of records and their quality assessments"
)
async def export_records_with_appraisals_json(run_id: str):
    stmt = SAselect(
        Record.id.label("record_id"),
        Record.title,
        Record.abstract,
        Record.authors,
        Record.year,
        Record.doi,
        Record.url,
        case((Record.source == "Scholar", "GoogleScholar"), else_=Record.source).label("source"),
        Record.publication_type,
        Record.institution,
        Appraisal.rating,
        Appraisal.score_final,
        Appraisal.rationale,
        Record.run_id,
    ).where(
        Record.run_id == run_id,
        Appraisal.run_id == run_id,
        Appraisal.record_id == Record.id,
    )
    rows = await _select_mappings(stmt)
    return _annotate_full_text_usage(run_id, rows)

@app.get("/runs/{run_id}/records_with_appraisals.csv")
async def export_records_with_appraisals_csv(run_id: str):
    stmt = SAselect(
        Record.id.label("record_id"),
        Record.title,
        Record.abstract,
        Record.authors,
        Record.year,
        Record.doi,
        Record.url,
        case((Record.source == "Scholar", "GoogleScholar"), else_=Record.source).label("source"),
        Record.publication_type,
        Record.institution,
        Appraisal.rating,
        Appraisal.score_final,
        Appraisal.rationale,
        Record.run_id,
    ).where(
        Record.run_id == run_id,
        Appraisal.run_id == run_id,
        Appraisal.record_id == Record.id,
    )
    rows = _annotate_full_text_usage(run_id, await _select_mappings(stmt))
    csv_body = _mappings_to_csv(rows, JOIN_COLS)
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=records_with_appraisals_{run_id}.csv"}
    )

# ======================= PRISMA summary ======================================

@app.get(
    "/runs/{run_id}/prisma.summary.json",
    tags=["export"],
    summary="Get PRISMA flow statistics",
    description="Retrieve PRISMA flow diagram data including identification, deduplication, screening, and inclusion counts with exclusion reasons",
    response_description="PRISMA statistics and exclusion reason breakdown"
)
async def prisma_summary_json(run_id: str):
    # Counts
    counts = None
    if PrismaCounts is not None:
        rows = await _select_stmt(SAselect(PrismaCounts).where(PrismaCounts.run_id == run_id))
        if rows:
            c = rows[0]
            counts = {
                "identified": getattr(c, "identified", 0),
                "deduped": getattr(c, "deduped", 0),
                "screened": getattr(c, "screened", 0),
                "excluded": getattr(c, "excluded", 0),
                "eligible": getattr(c, "eligible", 0),
                "included": getattr(c, "included", 0),
            }
    if counts is None:
        counts = {"identified": 0, "deduped": 0, "screened": 0, "excluded": 0, "eligible": 0, "included": 0}

    # Exclusion reasons
    reasons: dict[str, int] = {}
    if Screening is not None:
        reason_stmt = SAselect(
            Screening.reason.label("reason"),
            func.count().label("count")
        ).where(
            Screening.run_id == run_id,
            Screening.decision == "exclude",
        ).group_by(Screening.reason)
        rows = await _select_mappings(reason_stmt)
        for m in rows:
            key = m.get("reason") or "Unspecified"
            try:
                reasons[str(key)] = int(m.get("count") or 0)
            except Exception:
                reasons[str(key)] = 0

    return {"run_id": run_id, "counts": counts, "exclude_reasons": reasons}

@app.get("/runs/{run_id}/prisma.summary.csv")
async def prisma_summary_csv(run_id: str):
    data = await prisma_summary_json(run_id)
    # Flatten into two CSV sections: counts and reasons
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["metric", "value"])
    for k in ["identified", "deduped", "screened", "excluded", "eligible", "included"]:
        w.writerow([k, data["counts"].get(k, 0)])
    w.writerow([])
    w.writerow(["reason", "count"])
    for k, v in sorted(data.get("exclude_reasons", {}).items(), key=lambda kv: (-kv[1], kv[0])):
        w.writerow([k, v])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=records_export_{run_id}.csv"}
    )

# ======================= Joined export: paged + filtered =====================

@app.get("/runs/{run_id}/records_with_appraisals.page.json")
async def export_records_with_appraisals_page(
    run_id: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    order_by: str = Query("score_final", description="score_final|year|rating|source|title"),
    order_dir: str = Query("desc", description="asc|desc"),
    label_in: Optional[str] = Query(None, description="Comma-separated list: Red,Amber,Green"),
    label_order: Optional[str] = Query(None, description="Custom order for rating e.g., Green,Amber,Red"),
    score_min: Optional[float] = Query(None),
    score_max: Optional[float] = Query(None),
    year_min: Optional[int] = Query(None),
    year_max: Optional[int] = Query(None),
    source_in: Optional[str] = Query(None, description="Comma-separated sources"),
    q: Optional[str] = Query(None, description="Search in title/abstract"),
):
    R = Record
    A = Appraisal

    stmt = SAselect(
        R.id.label("record_id"),
        R.title,
        R.abstract,
        R.authors,
        R.year,
        R.doi,
        R.url,
        R.pdf_url,
        R.fulltext_url,
        R.open_access,
        R.source,
        R.publication_type,
        R.institution,
        A.rating,
        A.score_final,
        A.rationale,
        A.content_type,
        A.content_source,
        R.run_id,
    ).where(
        R.run_id == run_id,
        A.run_id == run_id,
        A.record_id == R.id,
    )

    # Filters
    if label_in:
        labs = [s.strip() for s in label_in.split(",") if s.strip()]
        if labs:
            stmt = stmt.where(A.rating.in_(labs))

    if score_min is not None:
        stmt = stmt.where((A.score_final >= score_min) | (A.score_final.is_(None)))
    if score_max is not None:
        stmt = stmt.where((A.score_final <= score_max) | (A.score_final.is_(None)))

    if year_min is not None:
        stmt = stmt.where((R.year >= year_min) | (R.year.is_(None)))
    if year_max is not None:
        stmt = stmt.where((R.year <= year_max) | (R.year.is_(None)))

    if source_in:
        srcs = [s.strip() for s in source_in.split(",") if s.strip()]
        if srcs:
            stmt = stmt.where(R.source.in_(srcs))

    if q:
        ql = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(R.title).like(ql), func.lower(R.abstract).like(ql))
        )

    # Ordering
    order_by = (order_by or "score_final").lower()
    if order_by == "score_final":
        order_col = A.score_final
    elif order_by == "year":
        order_col = R.year
    elif order_by == "rating":
        if label_order:
            order = [s.strip() for s in label_order.split(",") if s.strip()]
        else:
            order = ["Green", "Amber", "Red"]
        order_col = _label_rank_expr(A.rating, order)
    elif order_by == "source":
        order_col = R.source
    elif order_by == "title":
        order_col = R.title
    else:
        order_col = A.score_final

    # Direction
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

    # Count
    total = await _count_stmt(stmt)
    rows = _annotate_full_text_usage(run_id, await _select_mappings(stmt.offset(offset).limit(limit)))
    return {"run_id": run_id, "total": total, "limit": limit, "offset": offset, "items": rows}

# ======================= Screenings + Records export ==========================

SCREEN_COLS = [
    "record_id", "decision", "reason", "title", "authors", "year", "source", "doi", "url", "run_id"
]

@app.get("/runs/{run_id}/screenings_with_records.json")
async def export_screenings_with_records_json(run_id: str):
    S = Screening
    R = Record
    if S is None:
        raise HTTPException(status_code=404, detail="Screening model unavailable")
    stmt = SAselect(
        S.record_id.label("record_id"),
        S.decision.label("decision"),
        S.reason.label("reason"),
        R.title,
        R.authors,
        R.year,
        case((R.source == "Scholar", "GoogleScholar"), else_=R.source).label("source"),
        R.doi,
        R.url,
        R.run_id,
    ).where(
        S.run_id == run_id,
        R.run_id == run_id,
        S.record_id == R.id,
    )
    rows = await _select_mappings(stmt)
    return rows

@app.get("/runs/{run_id}/screenings_with_records.csv")
async def export_screenings_with_records_csv(run_id: str):
    S = Screening
    R = Record
    if S is None:
        raise HTTPException(status_code=404, detail="Screening model unavailable")
    stmt = SAselect(
        S.record_id.label("record_id"),
        S.decision.label("decision"),
        S.reason.label("reason"),
        R.title,
        R.authors,
        R.year,
        case((R.source == "Scholar", "GoogleScholar"), else_=R.source).label("source"),
        R.doi,
        R.url,
        R.run_id,
    ).where(
        S.run_id == run_id,
        R.run_id == run_id,
        S.record_id == R.id,
    )
    rows = await _select_mappings(stmt)
    csv_body = _mappings_to_csv(rows, SCREEN_COLS)
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=screenings_with_records_{run_id}.csv"}
    )

@app.get("/runs/{run_id}/screenings_with_records.page.json")
async def export_screenings_with_records_page(
    run_id: str,
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    decision: Optional[str] = Query(None, description="include|exclude"),
    reason_in: Optional[str] = Query(None, description="Comma-separated reasons"),
    source_in: Optional[str] = Query(None, description="Comma-separated sources"),
    year_min: Optional[int] = Query(None),
    year_max: Optional[int] = Query(None),
    q: Optional[str] = Query(None, description="Search in title/abstract"),
    order_by: str = Query("year", description="year|source|reason|title"),
    order_dir: str = Query("desc", description="asc|desc"),
):
    S = Screening
    R = Record
    if S is None:
        raise HTTPException(status_code=404, detail="Screening model unavailable")

    stmt = SAselect(
        S.record_id.label("record_id"),
        S.decision.label("decision"),
        S.reason.label("reason"),
        R.title,
        R.abstract,
        R.authors,
        R.year,
        case((R.source == "Scholar", "GoogleScholar"), else_=R.source).label("source"),
        R.doi,
        R.url,
        R.pdf_url,
        R.fulltext_url,
        R.open_access,
        R.run_id,
    ).where(
        S.run_id == run_id,
        R.run_id == run_id,
        S.record_id == R.id,
    )

    if decision in ("include", "exclude"):
        stmt = stmt.where(S.decision == decision)
    if reason_in:
        reasons = [s.strip() for s in reason_in.split(',') if s.strip()]
        if reasons:
            stmt = stmt.where(S.reason.in_(reasons))
    if source_in:
        srcs = [s.strip() for s in source_in.split(',') if s.strip()]
        if srcs:
            stmt = stmt.where(R.source.in_(srcs))
    if year_min is not None:
        stmt = stmt.where((R.year >= year_min) | (R.year.is_(None)))
    if year_max is not None:
        stmt = stmt.where((R.year <= year_max) | (R.year.is_(None)))
    if q:
        ql = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(R.title).like(ql), func.lower(R.abstract).like(ql)))

    # Order by
    ob = (order_by or "year").lower()
    if ob == "year":
        ob_col = R.year
    elif ob == "source":
        ob_col = R.source
    elif ob == "reason":
        ob_col = S.reason
    elif ob == "title":
        ob_col = R.title
    else:
        ob_col = R.year
    if order_dir.lower() == "desc":
        try:
            ob_col = ob_col.desc().nulls_last()
        except Exception:
            ob_col = ob_col.desc()
    else:
        try:
            ob_col = ob_col.asc().nulls_last()
        except Exception:
            ob_col = ob_col.asc()
    stmt = stmt.order_by(ob_col)

    total = await _count_stmt(stmt)
    rows = await _select_mappings(stmt.offset(offset).limit(limit))
    return {"run_id": run_id, "total": total, "limit": limit, "offset": offset, "items": rows}

# ======================= Runs list (paged) ===================================

def _dt_iso(dt_obj):
    try:
        return dt_obj.isoformat()
    except Exception:
        return str(dt_obj)

@app.get(
    "/runs.page.json",
    tags=["export"],
    summary="List literature review runs",
    description="Get paginated list of all literature review workflow executions with summary statistics",
    response_description="Paginated list of runs with record counts and quality distribution"
)
async def runs_page(
    limit: int = Query(20, ge=1, le=200, description="Number of runs to return per page"),
    offset: int = Query(0, ge=0, description="Number of runs to skip for pagination"),
):
    # Fetch page of runs
    runs_stmt = (
        SAselect(_db.SearchRun.id, _db.SearchRun.query, _db.SearchRun.created_at)
        .order_by(_db.SearchRun.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    run_rows = await _select_mappings(runs_stmt)
    run_ids = [r["id"] for r in run_rows]

    # Totals
    total_stmt = SAselect(func.count()).select_from(_db.SearchRun)
    total = await _count_stmt(SAselect(_db.SearchRun))  # use count of select *
    try:
        # more accurate count
        total = await _count_stmt(SAselect(_db.SearchRun.id))
    except Exception:
        pass

    # Aggregate counts for this page
    rec_counts = {}
    if run_ids:
        rc_stmt = (
            SAselect(Record.run_id, func.count().label("n"))
            .where(Record.run_id.in_(run_ids))
            .group_by(Record.run_id)
        )
        for m in await _select_mappings(rc_stmt):
            rec_counts[m["run_id"]] = int(m["n"])

    app_counts = {}
    label_counts: dict[str, dict[str, int]] = {}
    if run_ids:
        ac_stmt = (
            SAselect(Appraisal.run_id, func.count().label("n"))
            .where(Appraisal.run_id.in_(run_ids))
            .group_by(Appraisal.run_id)
        )
        for m in await _select_mappings(ac_stmt):
            app_counts[m["run_id"]] = int(m["n"])

        lab_stmt = (
            SAselect(Appraisal.run_id, Appraisal.rating, func.count().label("n"))
            .where(Appraisal.run_id.in_(run_ids))
            .group_by(Appraisal.run_id, Appraisal.rating)
        )
        for m in await _select_mappings(lab_stmt):
            rid = m["run_id"]
            lab = m["rating"] or ""
            n = int(m["n"])
            label_counts.setdefault(rid, {})[lab] = n

    items = []
    for r in run_rows:
        rid = r["id"]
        items.append({
            "id": rid,
            "query": r.get("query"),
            "created_at": _dt_iso(r.get("created_at")),
            "n_records": int(rec_counts.get(rid, 0)),
            "n_appraisals": int(app_counts.get(rid, 0)),
            "label_counts": label_counts.get(rid, {}),
        })

    return {"total": total, "limit": limit, "offset": offset, "items": items}

# ======================= Run summary =========================================

@app.get(
    "/runs/{run_id}/summary.json",
    tags=["export"],
    summary="Get comprehensive run summary",
    description="Retrieve detailed statistics and analytics for a literature review run including PRISMA counts, quality distribution, and source breakdown",
    response_description="Complete run analytics with counts, ratings, and source statistics"
)
async def run_summary(run_id: str):
    # Basic run info
    run_info = None
    rows = await _select_mappings(SAselect(_db.SearchRun.id, _db.SearchRun.query, _db.SearchRun.created_at).where(_db.SearchRun.id == run_id))
    if rows:
        r = rows[0]
        run_info = {"id": r["id"], "query": r.get("query"), "created_at": _dt_iso(r.get("created_at"))}
    else:
        run_info = {"id": run_id}

    # Counts
    counts = {"identified": 0, "deduped": 0, "screened": 0, "excluded": 0, "eligible": 0, "included": 0}
    if PrismaCounts is not None:
        pc_rows = await _select_stmt(SAselect(PrismaCounts).where(PrismaCounts.run_id == run_id))
        if pc_rows:
            c = pc_rows[0]
            counts = {
                "identified": int(getattr(c, "identified", 0) or 0),
                "deduped": int(getattr(c, "deduped", 0) or 0),
                "screened": int(getattr(c, "screened", 0) or 0),
                "excluded": int(getattr(c, "excluded", 0) or 0),
                "eligible": int(getattr(c, "eligible", 0) or 0),
                "included": int(getattr(c, "included", 0) or 0),
            }

    # Exclusion reasons
    reasons: dict[str, int] = {}
    if Screening is not None:
        rs = await _select_mappings(
            SAselect(Screening.reason.label("reason"), func.count().label("n")).where(
                Screening.run_id == run_id, Screening.decision == "exclude"
            ).group_by(Screening.reason)
        )
        for m in rs:
            key = m.get("reason") or "Unspecified"
            reasons[str(key)] = int(m.get("n") or 0)

    # Label distribution and counts
    n_records = 0
    rc = await _select_mappings(SAselect(func.count().label("n")).where(Record.run_id == run_id))
    if rc:
        try:
            n_records = int(rc[0].get("n") or 0)
        except Exception:
            n_records = 0
    n_appraisals = 0
    lab_counts: dict[str, int] = {}
    ac = await _select_mappings(SAselect(Appraisal.rating, func.count().label("n")).where(Appraisal.run_id == run_id).group_by(Appraisal.rating))
    for m in ac:
        lab_counts[m.get("rating") or ""] = int(m.get("n") or 0)
        n_appraisals += int(m.get("n") or 0)

    # Per-source counts for kept records
    per_source = {}
    ps = await _select_mappings(SAselect(Record.source, func.count().label("n")).where(Record.run_id == run_id).group_by(Record.source))
    for m in ps:
        src = m.get("source") or "Unknown"
        if src == "Scholar":
            src = "GoogleScholar"
        per_source[src] = int(m.get("n") or 0)

    return {
        "run": run_info,
        "counts": counts,
        "exclude_reasons": reasons,
        "n_records": n_records,
        "n_appraisals": n_appraisals,
        "label_counts": lab_counts,
        "source_counts_kept": per_source,
        "timings": {},
    }

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


# ======================= PRESS planner (LICO-aware) =======================

def _split_terms(s: str | None) -> list[str]:
    """Split free text into candidate terms; keep the full phrase too if multiword."""
    s = strip_or_empty(s)
    if not s:
        return []
    out = set()
    parts = re.split(r"[;,/]|(?i:\band\b)|(?i:\bor\b)", s)
    for p in parts:
        p = strip_or_empty(p)
        if p:
            out.add(p)
    if " " in s:
        out.add(s)
    return [t for t in sorted(out, key=len, reverse=True)]

def _tiab_expr(terms: list[str]) -> str:
    """
    Turn terms into PubMed [tiab] expressions.
    - Multiword terms are quoted: "foo bar"[tiab]
    - Single words get * wildcard if alnum and 4+ chars and not already wildcarded
    """
    out = []
    for t in terms:
        qt = strip_or_empty(t).strip('"')
        if not qt:
            continue
        if " " in qt:
            out.append(f"\"{qt}\"[tiab]")
        else:
            if re.fullmatch(r"[A-Za-z0-9\\-]+", qt) and len(qt) >= 4 and not qt.endswith("*"):
                out.append(f"{qt}*[tiab]")
            else:
                out.append(f"{qt}[tiab]")
    return " OR ".join(out) if out else ""

def _load_press_template(name: str | None) -> dict:
    import yaml
    tpl_name = strip_or_empty(name or os.getenv("PRESS_TEMPLATE", "education")).lower()
    candidates = [
        os.path.join("app", "press_templates", f"{tpl_name}.yaml"),
        os.path.join("press_templates", f"{tpl_name}.yaml"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    # fallback to general
    fallback = os.path.join("app", "press_templates", "general.yaml")
    if os.path.exists(fallback):
        with open(fallback, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {"id": "general", "facets": [], "limits": {"years_default": os.getenv("PRESS_YEAR_MIN", "2019-")}}

def _facet_text_for_pubmed(mesh: list[str] | None, text_words: list[str] | None, lico_terms: list[str], use_stock: bool) -> str:
    parts = []
    if use_stock and mesh:
        parts.append(" OR ".join([f'"{m}"[Mesh]' for m in mesh]))
    if use_stock and text_words:
        parts.append(" OR ".join([_tiab_expr([w]) for w in text_words]))
    if lico_terms:
        parts.append(_tiab_expr(lico_terms))
    return "(" + " OR ".join([p for p in parts if p]) + ")" if parts else ""

def _press_strategy_medline(lico: LICO, *, template: str | None = None, use_stock: bool = True, db_name: str = "MEDLINE", interface: str = "PubMed", years_override: str | None = None) -> dict:
    """Build MEDLINE/PubMed strategy using a configurable template and optional LICO merge."""
    tpl = _load_press_template(template)
    facets = tpl.get("facets") or []
    limits = tpl.get("limits") or {}
    years = years_override or limits.get("years_default") or os.getenv("PRESS_YEAR_MIN", "2019-")

    lico_map = {
        "learner": _split_terms(getattr(lico, 'learner', None)),
        "intervention": _split_terms(getattr(lico, 'intervention', None)),
        "context": _split_terms(getattr(lico, 'context', None)),
        "outcome": _split_terms(getattr(lico, 'outcome', None)),
    }

    # Build facet lines; skip empty ones, then number sequentially
    raw_facet_lines = []
    for facet in facets:
        fname = strip_or_empty(facet.get("name", "")).lower()
        mesh = facet.get("mesh") or []
        tw = facet.get("text_words") or []
        l_terms: list[str] = []
        if "learner" in fname:
            l_terms = lico_map["learner"]
        elif "intervention" in fname:
            l_terms = lico_map["intervention"]
        elif "context" in fname:
            l_terms = lico_map["context"]
        elif "outcome" in fname:
            l_terms = lico_map["outcome"]
        facet_text = _facet_text_for_pubmed(mesh, tw, l_terms, use_stock)
        # Map facet name to allowed StrategyLine.type, else fall back to "Text"
        if "learner" in fname:
            line_type = "Learner"
        elif "intervention" in fname:
            line_type = "Intervention"
        elif "context" in fname:
            line_type = "Context"
        elif "outcome" in fname:
            line_type = "Outcome"
        else:
            line_type = "Text"
        if facet_text:
            raw_facet_lines.append({"type": line_type, "text": facet_text})

    lines = []
    if raw_facet_lines:
        for i, lf in enumerate(raw_facet_lines, start=1):
            lines.append({"n": i, "type": lf["type"], "text": lf["text"], "hits": None})
        combine = " AND ".join([str(i) for i in range(1, len(raw_facet_lines)+1)])
        lines.append({"n": len(raw_facet_lines)+1, "type": "Combine", "text": combine, "hits": None})

    lim_parts = []
    if isinstance(years, str) and years.endswith("-"):
        y0 = years[:-1]
        if y0.isdigit():
            lim_parts.append(f"{y0}:3000[dp]")
    if limits.get("language_default"):
        lim_parts.append(f"{limits['language_default']}[la]")
    if limits.get("humans_default"):
        lim_parts.append("Humans[Mesh]")
    if lim_parts:
        # If there were no facet lines, start numbering at 1
        next_n = (lines[-1]["n"] + 1) if lines else 1
        lines.append({"n": next_n, "type": "Limits", "text": " AND ".join(lim_parts), "hits": None})

    return {"database": db_name, "interface": interface, "lines": lines}

def plan_press_from_lico(lico: LICO, databases: Optional[List[DatabaseSpec]] = None, *, template: str | None = None, use_stock: bool = True, years: str | None = None) -> dict:
    """Return a PRESS-compatible plan dict (question_lico + strategies + checklist)."""
    dbs = databases or [DatabaseSpec(name="MEDLINE", interface="PubMed")]
    db = dbs[0]
    strat = _press_strategy_medline(lico, template=template, use_stock=use_stock, db_name=db.name or "MEDLINE", interface=db.interface or "PubMed", years_override=years)

    has_custom = any([
        strip_or_empty(getattr(lico, 'learner', None)),
        strip_or_empty(getattr(lico, 'intervention', None)),
        strip_or_empty(getattr(lico, 'context', None)),
        strip_or_empty(getattr(lico, 'outcome', None)),
    ])
    checklist = {
        "translation": "pass",
        "subject_headings": "pass" if use_stock else "suggest",
        "text_words": "pass" if has_custom else "suggest",
        "spelling_syntax_lines": "pass",
        "limits_filters": "pass",
        "notes": "Auto-checks are heuristic; librarian review recommended.",
    }

    return {
        "question_lico": {
            "learner": (lico.learner or ""),
            "intervention": (lico.intervention or ""),
            "context": (lico.context or ""),
            "outcome": (lico.outcome or ""),
        },
        "strategies": {
            "MEDLINE": strat
        },
        "checklist": {
            "MEDLINE": checklist
        }
    }

# --- Small adapters so fill_hits_for_pubmed can accept our dict strategy ------

def _strategy_dict_to_ns(strategy: dict) -> _NS:
    """Convert our dict strategy to an object with .database/.interface/.lines attrs."""
    lines = [ _NS(**ln) for ln in strategy.get("lines", []) ]
    return _NS(database=strategy.get("database"),
               interface=strategy.get("interface"),
               lines=lines)

def _strategy_ns_to_dict(ns: _NS) -> dict:
    return {
        "database": getattr(ns, "database", None),
        "interface": getattr(ns, "interface", None),
        "lines": [
            {
                "n": getattr(ln, "n", None),
                "type": getattr(ln, "type", None),
                "text": getattr(ln, "text", None),
                "hits": getattr(ln, "hits", None),
            }
            for ln in getattr(ns, "lines", []) or []
        ],
    }

# ----------------------- PRESS planner endpoints ------------------------------

class PressPlanBody(BaseModel):
    """Request model for generating PRESS search strategies."""
    lico: LICO
    databases: Optional[List[DatabaseSpec]] = None
    template: Optional[str] = None
    use_stock: Optional[bool] = True
    enable_ai: Optional[bool] = False
    research_domain: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "lico": {
                        "learner": "nursing students",
                        "intervention": "problem-based learning",
                        "context": "undergraduate nursing education",
                        "outcome": "critical thinking skills"
                    },
                    "template": "education",
                    "use_stock": True,
                    "enable_ai": True,
                    "research_domain": "healthcare education"
                },
                {
                    "lico": {
                        "learner": "patients with diabetes",
                        "intervention": "mobile health applications",
                        "context": "self-management",
                        "outcome": "glycemic control"
                    },
                    "template": "clinical",
                    "use_stock": True,
                    "enable_ai": False
                }
            ]
        }
    }

@app.post(
    "/press/plan",
    response_model=PressPlanResponse,
    tags=["press"],
    summary="Generate PRESS search strategy",
    description="Create a structured PRESS (Peer Review of Electronic Search Strategies) plan from LICO components with domain-specific templates and validation checklist",
    response_description="Complete PRESS strategy with numbered search lines and quality checklist"
)
async def make_press_plan(body: PressPlanBody):
    """Return a PRESS-compatible, LICO-driven strategy (numbered boolean lines + self-check)."""
    return plan_press_from_lico(body.lico, body.databases, template=body.template, use_stock=bool(body.use_stock))


@app.post(
    "/press/plan/ai-enhanced",
    response_model=dict,
    tags=["press", "ai"],
    summary="Generate AI-enhanced PRESS strategy",
    description="Create an intelligent PRESS plan with AI-powered LICO term suggestions, strategy analysis, and optimization recommendations",
    response_description="Enhanced PRESS plan with AI insights and improvement suggestions"
)
async def make_ai_enhanced_press_plan(body: PressPlanBody):
    """
    Return an AI-enhanced PRESS plan with intelligent suggestions and analysis.
    Combines traditional PRESS planning with AI-powered enhancements.
    """
    # Generate basic plan
    base_plan = plan_press_from_lico(body.lico, body.databases, template=body.template, use_stock=bool(body.use_stock))
    
    result = {
        "base_plan": base_plan,
        "ai_enhancement": None,
        "strategy_analysis": None,
        "ai_available": False
    }
    
    # Add AI enhancements if requested and available
    if body.enable_ai:
        ai_service = get_ai_service()
        if ai_service.is_available():
            result["ai_available"] = True
            
            try:
                # Get AI LICO enhancement suggestions
                enhancement = await ai_service.enhance_lico_terms(
                    lico=body.lico,
                    research_domain=body.research_domain
                )
                result["ai_enhancement"] = enhancement
                
                # Analyze the generated strategy
                strategy_lines = []
                if base_plan.get("strategies") and "MEDLINE" in base_plan["strategies"]:
                    lines = base_plan["strategies"]["MEDLINE"].get("lines", [])
                    strategy_lines = [{"type": line.get("type"), "text": line.get("text")} for line in lines]
                
                if strategy_lines:
                    analysis = await ai_service.analyze_press_strategy(strategy_lines)
                    result["strategy_analysis"] = analysis
                
            except Exception as e:
                result["ai_error"] = str(e)
    
    return result

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
    plan = plan_press_from_lico(body.lico, body.databases, template=body.template, use_stock=bool(body.use_stock))
    # fill for MEDLINE/PubMed only
    strat = plan.get("strategies", {}).get("MEDLINE")
    if strat:
        ns = _strategy_dict_to_ns(strat)
        ns = await fill_hits_for_pubmed(ns)  # expects attrs
        plan["strategies"]["MEDLINE"] = _strategy_ns_to_dict(ns)
    return plan

class LICOPreviewBody(BaseModel):
    """Request model for LICO preview functionality."""
    lico: LICO

@app.post("/press/plan/preview")
async def preview_press_strategy(body: LICOPreviewBody):
    """Preview how LICO terms will be integrated into PRESS search strategy."""
    # Force reload to register endpoint
    try:
        from app.press import plan_press_from_lico, _extract_user_terms, _load_terms, _merge_terms_with_yaml

        # Load existing YAML terms for comparison
        terms = _load_terms("config/press_terms.yaml")

        # Extract user terms from each LICO component
        user_terms = {
            "learner": _extract_user_terms(body.lico.learner),
            "intervention": _extract_user_terms(body.lico.intervention),
            "context": _extract_user_terms(body.lico.context),
            "outcome": _extract_user_terms(body.lico.outcome)
        }

        # Show merged terms for each component
        merged_terms = {}
        for component in ["learner", "intervention", "context", "outcome"]:
            yaml_component_terms = terms.get(component, {})
            user_component_terms = user_terms[component]
            merged = _merge_terms_with_yaml(user_component_terms, yaml_component_terms)

            merged_terms[component] = {
                "user_extracted": user_component_terms,
                "yaml_mesh": yaml_component_terms.get("mesh", []),
                "yaml_text": yaml_component_terms.get("text", []),
                "final_mesh": merged["mesh"],
                "final_text": merged["text"]
            }

        # Generate full PRESS plan for demonstration
        press_plan = plan_press_from_lico(body.lico)

        return {
            "lico_input": body.lico.model_dump(),
            "extracted_terms": user_terms,
            "merged_terms": merged_terms,
            "sample_strategy": press_plan.strategies.get("MEDLINE", {}).model_dump() if press_plan.strategies.get("MEDLINE") else {},
            "message": "This preview shows how your LICO terms will be integrated with existing search terms"
        }

    except Exception as e:
        logger.error(f"Error generating PRESS preview: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")

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
    strat = base.get("strategies", {}).get("MEDLINE")
    if strat and db_name == "MEDLINE" and (interface or "PubMed").lower() == "pubmed":
        ns = _strategy_dict_to_ns(strat)
        ns = await fill_hits_for_pubmed(ns)
        base["strategies"]["MEDLINE"] = _strategy_ns_to_dict(ns)
    return base


# --- AI-Enhanced Features ----------------------------------------------------

class LICOEnhancementRequest(BaseModel):
    lico: LICO
    research_domain: Optional[str] = None


class PressStrategyAnalysisRequest(BaseModel):
    strategy_lines: List[dict]


class StudyRelevanceRequest(BaseModel):
    title: str
    abstract: Optional[str] = None
    inclusion_criteria: List[str] = []
    exclusion_criteria: List[str] = []
    research_question: Optional[str] = None


@app.post(
    "/ai/enhance-lico",
    response_model=Optional[LICOEnhancement],
    tags=["ai"],
    summary="AI-powered LICO term enhancement",
    description="Get intelligent suggestions to expand and improve LICO (Learner, Intervention, Context, Outcome) terms for comprehensive literature search coverage",
    response_description="Enhanced LICO terms with synonyms, MeSH headings, and related concepts"
)
async def ai_enhance_lico(request: LICOEnhancementRequest):
    """
    Get AI-powered suggestions to enhance LICO terms for better search coverage.
    Provides synonyms, related terms, MeSH suggestions, and template recommendations.
    """
    ai_service = get_ai_service()
    if not ai_service.is_available():
        raise HTTPException(status_code=503, detail="AI service unavailable. Check OPENAI_API_KEY configuration.")
    
    try:
        enhancement = await ai_service.enhance_lico_terms(
            lico=request.lico,
            research_domain=request.research_domain
        )
        return enhancement
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI enhancement failed: {str(e)}")


@app.post(
    "/ai/analyze-strategy",
    response_model=Optional[PressStrategyAnalysis],
    tags=["ai"],
    summary="AI analysis of PRESS search strategy",
    description="Get expert AI evaluation of search strategy completeness, balance, and effectiveness with specific improvement recommendations",
    response_description="Detailed strategy analysis with quality scores and optimization suggestions"
)
async def ai_analyze_press_strategy(request: PressStrategyAnalysisRequest):
    """
    Get AI analysis of a PRESS search strategy with suggestions for improvement.
    Evaluates completeness, balance, and provides specific recommendations.
    """
    ai_service = get_ai_service()
    if not ai_service.is_available():
        raise HTTPException(status_code=503, detail="AI service unavailable. Check OPENAI_API_KEY configuration.")
    
    try:
        analysis = await ai_service.analyze_press_strategy(
            strategy_lines=request.strategy_lines
        )
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


@app.post(
    "/ai/assess-relevance",
    response_model=Optional[StudyRelevanceAssessment],
    tags=["ai"],
    summary="AI study relevance assessment",
    description="Get intelligent evaluation of study relevance for systematic review inclusion with detailed reasoning and recommendations",
    response_description="Relevance assessment with inclusion/exclusion recommendation and reasoning"
)
async def ai_assess_study_relevance(request: StudyRelevanceRequest):
    """
    Get AI assessment of study relevance for systematic review inclusion.
    Provides detailed reasoning and inclusion/exclusion recommendations.
    """
    ai_service = get_ai_service()
    if not ai_service.is_available():
        raise HTTPException(status_code=503, detail="AI service unavailable. Check OPENAI_API_KEY configuration.")
    
    try:
        assessment = await ai_service.assess_study_relevance(
            title=request.title,
            abstract=request.abstract,
            inclusion_criteria=request.inclusion_criteria,
            exclusion_criteria=request.exclusion_criteria,
            research_question=request.research_question
        )
        return assessment
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI assessment failed: {str(e)}")


@app.post("/ai/suggest-template")
async def ai_suggest_template(lico: LICO):
    """
    Get smart template suggestion based on LICO content analysis.
    Returns the most appropriate template: clinical, education, or general.
    """
    ai_service = get_ai_service()
    try:
        suggested_template = ai_service.suggest_template(lico)
        return {
            "suggested_template": suggested_template,
            "available_templates": ["clinical", "education", "general"],
            "reasoning": f"Based on the content analysis, the '{suggested_template}' template best matches your research focus."
        }
    except Exception as e:
        return {
            "suggested_template": "general",
            "available_templates": ["clinical", "education", "general"], 
            "reasoning": "Default template selected due to analysis error.",
            "error": str(e)
        }


# Request models for new AI endpoints
class ResearchQuestionRequest(BaseModel):
    question: str

class LICORequest(BaseModel):
    lico: LICO


@app.post("/ai/generate-question")
async def ai_generate_research_question(request: LICORequest):
    """
    Generate an academic research question from LICO components.
    """
    ai_service = get_ai_service()
    try:
        question = await ai_service.generate_research_question(request.lico)
        if question is None:
            raise HTTPException(status_code=503, detail="AI service unavailable")
        return {"question": question}
    except Exception as e:
        logger.error(f"Error generating research question: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate research question: {str(e)}")


@app.post("/ai/extract-lico")
async def ai_extract_lico_from_question(request: ResearchQuestionRequest):
    """
    Extract LICO components from a research question.
    """
    ai_service = get_ai_service()
    try:
        lico = await ai_service.extract_lico_from_question(request.question)
        if lico is None:
            raise HTTPException(status_code=503, detail="AI service unavailable")

        response = {"lico": lico}
        logger.info(f"LICO extraction response: {response}")
        return response
    except Exception as e:
        logger.error(f"Error extracting LICO from question: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to extract LICO: {str(e)}")


@app.post("/ai/enhance-question")
async def ai_enhance_research_question(request: ResearchQuestionRequest):
    """
    Enhance and improve a research question for systematic review quality.
    """
    ai_service = get_ai_service()
    try:
        enhanced_question = await ai_service.enhance_research_question(request.question)
        if enhanced_question is None:
            raise HTTPException(status_code=503, detail="AI service unavailable")
        return {"enhanced_question": enhanced_question}
    except Exception as e:
        logger.error(f"Error enhancing research question: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enhance research question: {str(e)}")


class ResearchSynthesisRequest(BaseModel):
    """Request model for research synthesis"""
    research_question: Optional[str] = None
    lico_components: Optional[dict] = None
    include_fulltext: bool = True
    max_studies: int = 50

@app.post(
    "/runs/{run_id}/synthesis",
    response_model=ResearchSynthesis,
    tags=["ai"],
    summary="Generate AI research synthesis",
    description="Create comprehensive evidence-based research synthesis with full-text analysis, LICO insights, and actionable recommendations",
    response_description="Complete research synthesis with evidence analysis and recommendations"
)
def generate_research_synthesis(run_id: str, request: ResearchSynthesisRequest):
    """
    Generate comprehensive AI research synthesis for a literature review run.
    Analyzes all appraised studies, retrieves full text when available,
    and provides evidence-based answers to LICO research questions.
    """
    try:
        # Use synchronous database access to avoid async issues
        from app.db import get_session
        from sqlalchemy import text
        
        with get_session() as db:
            # Get records with appraisals using a simple query
            query = text("""
                SELECT 
                    r.id as record_id,
                    r.title,
                    r.abstract,
                    r.authors,
                    r.year,
                    r.doi,
                    r.url,
                    r.source,
                    r.publication_type,
                    a.rating as appraisal_color,
                    a.score_final as appraisal_score,
                    a.rationale as appraisal_reasoning,
                    r.run_id
                FROM records r
                LEFT JOIN appraisals a ON r.id = a.record_id
                WHERE r.run_id = :run_id AND a.run_id = :run_id
                ORDER BY COALESCE(a.score_final, 0) DESC
                LIMIT :max_studies
            """)
            
            result = db.execute(query, {
                "run_id": run_id, 
                "max_studies": request.max_studies
            })
            
            records_data = [dict(row._mapping) for row in result]
        
        if not records_data:
            raise HTTPException(status_code=404, detail=f"No appraised records found for run {run_id}")
        
        # Get research question from request or default
        research_question = request.research_question or "What does the evidence tell us about medical education interventions and their effectiveness?"
        
        logger.info(f"Starting research synthesis for run {run_id} with {len(records_data)} studies")
        
        # Extract study findings with full-text retrieval
        findings = extract_study_findings_sync(records_data, retrieve_fulltext=request.include_fulltext)

        # Track which studies contributed full text
        fulltext_usage: Dict[str, bool] = {}
        for record, finding in zip(records_data, findings):
            record_id = record.get("record_id")
            used_full_text = bool(
                finding.full_text_content is not None and getattr(finding.full_text_content, "extraction_success", False)
            )
            record["full_text_used"] = used_full_text
            if record_id:
                fulltext_usage[record_id] = used_full_text

        # Cache per-run usage for downstream exports
        FULLTEXT_USAGE_CACHE[run_id] = fulltext_usage

        # Generate comprehensive synthesis
        synthesis = synthesize_research_sync(
            findings=findings,
            original_question=research_question,
            lico_components=request.lico_components
        )

        # Ensure response exposes record-based availability
        if hasattr(synthesis, "full_text_availability"):
            synthesis.full_text_availability = fulltext_usage

        logger.info(f"Research synthesis completed for run {run_id}")
        return synthesis
        
    except Exception as e:
        logger.error(f"Research synthesis failed for run {run_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate research synthesis: {str(e)}")

@app.get(
    "/ai/status",
    tags=["ai"],
    summary="Check AI service status",
    description="Verify AI service availability and list supported intelligent research assistance features",
    response_description="AI service status and available features"
)
async def ai_status():
    """Check AI service availability and configuration."""
    ai_service = get_ai_service()
    return {
        "available": ai_service.is_available(),
        "model": ai_service.config.model if ai_service.is_available() else None,
        "features": [
            "LICO enhancement",
            "PRESS strategy analysis", 
            "Study relevance assessment",
            "Quality rationale generation",
            "Smart template selection",
            "Research synthesis with full-text retrieval"
        ] if ai_service.is_available() else []
    }

@app.get("/test/synthesis-imports")
async def test_synthesis_imports():
    """Test endpoint to debug synthesis import issues."""
    try:
        from app.research_synthesizer import extract_study_findings, synthesize_research, ResearchSynthesis
        return {"status": "success", "message": "All synthesis imports working"}
    except Exception as e:
        return {"status": "error", "message": f"Import failed: {str(e)}"}

@app.post("/test/minimal-synthesis/{run_id}")
def test_minimal_synthesis(run_id: str):
    """Minimal synthesis endpoint for debugging"""
    try:
        from app.research_synthesizer import ResearchSynthesis, LICOInsights, EvidenceSupport
        
        # Return a minimal valid response
        return ResearchSynthesis(
            executive_summary="This is a test synthesis response.",
            research_question_answer="Test answer to research question.",
            lico_insights=LICOInsights(
                learner_insights="Test learner insights",
                intervention_insights="Test intervention insights", 
                context_insights="Test context insights",
                outcome_insights="Test outcome insights"
            ),
            evidence_strength="Limited",
            confidence_level="Low",
            key_recommendations=["Test recommendation"],
            knowledge_gaps=["Test gap"],
            methodological_quality="Test quality",
            future_research_directions=["Test direction"],
            supporting_evidence=[],
            full_text_availability={}
        )
    except Exception as e:
        logger.error(f"Minimal synthesis test failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Minimal synthesis failed: {str(e)}")

@app.post("/test/real-synthesis/{run_id}")
def test_real_synthesis(run_id: str):
    """Real AI synthesis using actual research data"""
    try:
        from app.db import get_session
        from sqlalchemy import text
        from app.research_synthesizer import extract_study_findings, synthesize_research
        
        with get_session() as db:
            # Get records with appraisals using a simple query
            query = text("""
                SELECT 
                    r.id as record_id,
                    r.title,
                    r.abstract,
                    r.authors,
                    r.year,
                    r.doi,
                    r.url,
                    r.source,
                    r.publication_type,
                    a.rating as appraisal_color,
                    a.score_final as appraisal_score,
                    a.rationale as appraisal_reasoning,
                    r.run_id
                FROM records r
                LEFT JOIN appraisals a ON r.id = a.record_id
                WHERE r.run_id = :run_id AND a.run_id = :run_id
                ORDER BY COALESCE(a.score_final, 0) DESC
                LIMIT 10
            """)
            
            result = db.execute(query, {"run_id": run_id})
            records_data = [dict(row._mapping) for row in result]
        
        if not records_data:
            raise HTTPException(status_code=404, detail=f"No appraised records found for run {run_id}")
        
        # Extract study findings and generate synthesis
        findings = extract_study_findings(records_data, retrieve_fulltext=False)
        
        synthesis = synthesize_research(
            findings=findings,
            original_question="What does the evidence tell us about medical education interventions and their effectiveness in improving learning outcomes?",
            lico_components=None
        )
        
        return synthesis
        
    except Exception as e:
        logger.error(f"Real synthesis failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to generate real synthesis: {str(e)}")
