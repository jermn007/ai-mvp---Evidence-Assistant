# Changelog

## 2025-09-11 — PRESS planner fixes, robustness, and logging

Backend changes

- Safe string helpers: Adopted `app/utils/strings.py` (`strip_or_empty`, `norm_lower`) across PRESS and graph paths to eliminate `NoneType.strip()` errors.
  - `app/server.py`: Uses helpers in `_genericize_query`, `_split_terms`, `_tiab_expr`, `_load_press_template`, and PRESS LICO mapping/flags. Ensures `init_state["query"]` is safe.
  - `app/graph/nodes.py`: Normalizes query, sources, titles, abstracts, and authors for dedupe/screen; uses `norm_lower` for exact keys and similarity checks.

- Enhanced run_with_press observability:
  - `app/server.py`: Added step-by-step INFO logs around endpoint entry, plan handling, graph execution, and persistence; logs full tracebacks on failures.
  - Added a lightweight HTTP middleware to log all requests and responses with status codes.
  - Ensured module logger is configured (`basicConfig`) when no handlers are present so logs show up under uvicorn.

- Plan/strategy query handling:
  - `_expand_lines_to_queries` call guarded to tolerate missing/variant inputs.
  - `_genericize_query` now accepts `None` and normalizes safely before regex processing.

- SQLite schema compatibility (fixes 500 on persist):
  - `app/db.py`: Added `_ensure_sqlite_schema_compat()` to add any missing columns on existing SQLite DBs (e.g., `journal`, `conference`, `pmid`, `arxiv_id`, `open_access`, `cited_by_count`, `reference_count`, etc.) and ensure `appraisals.score_final` exists.
  - `init_db()` now calls the compatibility routine; `app/server.py` invokes `init_db()` at startup.
  - Result: `persist_run` now succeeds without “table records has no column named journal” errors.

Frontend changes

- LICO extraction wiring:
  - `frontend/press-planner/src/components/ResearchInput.tsx`: When extracting LICO from a question, update each LICO field unconditionally (normalize non-string to ""). Ensures the LICO Components UI reflects extracted values immediately.
  - `frontend/press-planner/src/components/PressPlanner.tsx`: During auto-extract in plan build, also update each LICO field unconditionally so plan creation uses extracted LICO consistently.

Misc

- Kept existing providers/sources intact; only hardened None handling and logging.
- Left noisy `PostgresSaver` warning untouched (non-fatal); see next steps to gate it behind config.

Next steps

- Migrations: Replace the SQLite compatibility shim with proper Alembic migrations.
  - Fill the empty `upgrade()` functions in:
    - `alembic/versions/0291ad88f3c3_add_authors_and_publication_type_to_.py`
    - `alembic/versions/5a2ea3e447f0_add_score_final_backfill_indexes.py`
    - `alembic/versions/e9ab59836f6b_add_extended_metadata_fields.py`
  - Then run `alembic upgrade head` (backup DB first) and remove the shim if desired.

- Gate PostgresSaver init behind config:
  - In `app/graph/build.py`, only attempt Postgres checkpointer when `CHECKPOINTER_URL` (or similar) is set to avoid repeated warnings in local/dev.

- Optional hardening:
  - Add more type guards in `app/ai_service.py` where `.strip()` is used on model outputs (already mostly safe via `or ''`).
  - Add unit tests for `_split_terms`, `_genericize_query`, and `nodes._dedupe_records` with edge-case inputs (None/empty).

- Docs:
  - README: Document how to run frontend: `cd frontend/press-planner && npm i && npm run dev` (API at `http://127.0.0.1:8000`).

