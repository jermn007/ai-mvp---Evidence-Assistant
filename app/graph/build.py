# app/graph/build.py
from __future__ import annotations
import os, re, warnings, atexit
from langgraph.graph import StateGraph, START, END
from app.graph.state import AgentState
from app.graph.nodes import plan_press, harvest, dedupe_screen, appraise, report_prisma

def _make_checkpointer():
    """Return a LangGraph checkpointer, preferring Postgres if configured.
    Works with both old (context manager) and new (plain object) APIs."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

    # Prefer Postgres if available
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except Exception as e:
        warnings.warn(f"PostgresSaver not importable ({e!r}); using MemorySaver.")
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

    # Checkpointer wants a psycopg3-style URL (no '+psycopg2')
    pg_url = re.sub(r"\+psycopg2", "", db_url)

    try:
        saver_or_cm = PostgresSaver.from_conn_string(pg_url)

        # If it's a context manager, enter it and keep it open until process exit
        if hasattr(saver_or_cm, "__enter__") and hasattr(saver_or_cm, "__exit__"):
            cm = saver_or_cm
            saver = cm.__enter__()  # acquire underlying saver
            atexit.register(lambda: cm.__exit__(None, None, None))
        else:
            saver = saver_or_cm

        # Create tables on first run if method exists (idempotent)
        if hasattr(saver, "setup"):
            try:
                saver.setup()
            except Exception:
                pass

        return saver

    except Exception as e:
        warnings.warn(f"PostgresSaver init failed ({e!r}); using MemorySaver.")
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()

# Create one process-wide checkpointer (so it stays open)
CHECKPOINTER = _make_checkpointer()

def get_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("plan_press", plan_press)
    workflow.add_node("harvest", harvest)
    workflow.add_node("dedupe_screen", dedupe_screen)
    workflow.add_node("appraise", appraise)
    workflow.add_node("report_prisma", report_prisma)

    workflow.add_edge(START, "plan_press")
    workflow.add_edge("plan_press", "harvest")
    workflow.add_edge("harvest", "dedupe_screen")
    workflow.add_edge("dedupe_screen", "appraise")
    workflow.add_edge("appraise", "report_prisma")
    workflow.add_edge("report_prisma", END)

    # Always compile with the global checkpointer
    return workflow.compile(checkpointer=CHECKPOINTER)
