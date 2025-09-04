# Evidence Assistant MVP — Project Report & Next Steps (Handoff)

_Last updated: 2025‑09‑03_

## Executive Summary
This MVP implements an end‑to‑end pipeline to turn a user’s education evidence question into:
- Multi‑source search (PubMed, Crossref, arXiv, ERIC, Semantic Scholar, Google Scholar via SerpAPI)
- Appraisal and scoring (RAG/Amber/Green labels and a numeric `score_final`)
- Persisted runs, records, and appraisals in PostgreSQL with LangGraph checkpointing
- A PRESS‑compatible search planning layer that accepts **LICO** inputs (Learner, Intervention, Context, Outcome) and emits PubMed/MEDLINE boolean lines
- Export & paging APIs for downstream UX and analysis

You can reliably spin up the API, run searches, see appraisals, export CSV/JSON, and generate PRESS plans (with PubMed hit counts). This report captures architecture, setup/runbook, API reference, troubleshooting fixes applied, and a prioritized next‑steps roadmap.

---

## Goals & Non‑Goals
**Goals**
- Provide reproducible evidence search and appraisal runs
- Offer PRESS‑aligned planning with LICO‑aware inputs
- Persist results, enable exports, and support simple dashboards/UX

**Non‑Goals (for MVP)**
- Full librarian‑grade PRESS QA
- Multi‑database hit counts beyond PubMed
- Advanced deduping/clustered ranking across sources

---

## High‑Level Architecture
```
┌───────────┐   query    ┌─────────────────────────────┐     persist        ┌────────────┐
│  Client   ├───────────►│  FastAPI app.server         ├───────────────────►│PostgreSQL  │
└─────┬─────┘            │  /run, exports, PRESS       │                    └────┬───────┘
      │                  └───────────────┬─────────────┘                         │
      │                                  │                                        │
      │                             invoke graph                                  │
      │                                  │                                        │
      ▼                  ┌───────────────▼─────────────┐                         │
  Frontend (Next)        │ LangGraph graph (app.graph) │                         │
  - Press Planner        │ nodes: retrieve, appraise    │                         │
  - Dashboard            └───────────────┬─────────────┘                         │
                                         │                                        │
                                         ▼                                        │
                              Source adapters (app.sources)                       │
                              PubMed/Crossref/arXiv/ERIC/S2/Scholar               │
```
**Persistence**
- Application tables: `records`, `appraisals` (+ `score_final` numeric)
- LangGraph checkpoint tables (ignored by Alembic autogenerate)

**Observability**
- `/health`, `/health/checkpointer`
- Structured exports & summary endpoints

---

## Setup & Runbook
### Prerequisites
- **Python 3.10+** (tested on 3.12)
- **PostgreSQL** (Docker container `langgraph-pg` recommended)
- Environment variables in `.env`: `DATABASE_URL`, API keys (e.g., OpenAI, SerpAPI)

### Install (Windows / PowerShell)
```powershell
# create venv
python -m venv .venv
. .\.venv\Scripts\Activate.ps1

# install deps
pip install -r requirements.txt

# start postgres (example docker)
docker start langgraph-pg  # or docker run ... if first time

# env for DB (if not in .env)
$env:DATABASE_URL = "postgresql+psycopg2://languser:changeme@localhost:5432/langgraph"
```

### Alembic (migrations)
We fixed Alembic templates and autogenerate. `env.py` excludes LangGraph checkpoint tables.
```powershell
# initialize only if not created
ython -m alembic init alembic

# create baseline from current models
python -m alembic revision -m "baseline" --autogenerate
python -m alembic upgrade head
```
**Backfill for `score_final` (if needed)**
```powershell
python -m app.scripts.backfill_score_final
```

### Run the API
```powershell
python -m uvicorn app.server:app --reload
```
Health:
- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/health/checkpointer`

### Smoke tests (PowerShell friendly)
```powershell
# 1) Create a run
$tid = [guid]::NewGuid().ToString()
$resp = Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/run" `
  -ContentType "application/json" -Body (@{ query="active learning in higher education"; thread_id=$tid } | ConvertTo-Json)
$RUN = $resp.run_id

# 2) Exports & paging
irm "http://127.0.0.1:8000/runs/$RUN/summary.json" | ConvertTo-Json -Depth 5
irm "http://127.0.0.1:8000/runs/$RUN/appraisals.page.json?score_min=0.7&order_by=score_final&order_dir=desc" | ConvertTo-Json -Depth 5

# 3) PRESS plan (LICO → plan, with PubMed counts)
$body = (@{ lico = @{ learner="prelicensure nursing"; intervention="simulation"; context="university"; outcome="skills" } } | ConvertTo-Json)
irm "http://127.0.0.1:8000/press/plan" -Method POST -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 8
irm "http://127.0.0.1:8000/press/plan/hits" -Method POST -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 8
```

---

## API Reference (MVP)
### Run & Health
- `POST /run` → `{ thread_id?, query }` → creates a run; returns `{ run_id, prisma, ratings, ... }`
- `GET /health` → `{ ok, env }`
- `GET /health/checkpointer` → `{ checkpointer }`

### Source sanity
- `GET /sources/test?q=...&max_n=5` → Per‑source counts/errors

### Exports
- `GET /runs/{run_id}/records.json|.csv`
- `GET /runs/{run_id}/appraisals.json|.csv`
- `GET /runs/{run_id}/summary.json`

### Paged appraisals
`GET /runs/{run_id}/appraisals.page.json`
- Query params: `limit`, `offset`, numeric filters `score_min|score_max` (prefer `score_final`), legacy numeric `rating_min|rating_max`, categorical `label_in`, ordinal `label_min` with optional `label_order` (default `Red,Amber,Green`), sort `order_by` one of `created_at|rating|score_final|id` with `order_dir`.

### PRESS Planner (LICO aware)
- `POST /press/plan` `{ lico: { learner, intervention, context, outcome }, databases? }` → PRESS plan with MEDLINE/PubMed lines (scaffold + your text‑words)
- `POST /press/plan/hits` → same but with PubMed hit counts (adapters convert dict ⇄ object for `fill_hits_for_pubmed`)
- `GET /runs/{run_id}/press.plan.json` → Build plan from a run (uses run query as `intervention` if no LICO provided)
- `GET /runs/{run_id}/press.plan.hits.json` → as above with PubMed counts

**Planner behavior**
- Merges stable MeSH scaffolding with your L/I/C/O text words. Multiword phrases are quoted; single words are wildcarded with `*` when safe.
- Adds separate Limits line (`2015:3000[dp] AND English[la] AND Humans[Mesh]`).

---

## Database Schema (App tables)
### records
- `id` (uuid), `run_id` (uuid), `title`, `abstract`, `year`, `doi`, `url`, `source`, `created_at`

### appraisals
- `id` (uuid), `run_id` (uuid), `record_id` (text), `rating` (text e.g., Red/Amber/Green or legacy numeric),
- `scores_json` (json), `rationale` (text), `citations_json` (json),
- **`score_final` (numeric)** ← **new** for numeric filtering/sorting
- `created_at` (timestamp)

### Alembic notes
- `env.py` excludes LangGraph checkpoint tables from autogenerate
- Baseline migration created; backfill script added for `score_final`

---

## Fixes Applied (Troubleshooting Log)
- **ImportError `async_session`** → Compatibility layer in `server.py` supports multiple session factories (`async_session`, `AsyncSessionLocal`, `SessionLocal`, `session`).
- **SQLAlchemy `or__` typo** → Corrected to `or_`.
- **Rating numeric filter errors (text vs numeric)** → `_numeric_like()` helper uses regex + `CAST(... AS FLOAT)` safely.
- **`score_final` missing** → Added column + Alembic migration + backfill script. Updated endpoints to prefer `score_final`.
- **Alembic template error (`script.py.mako`)** → Created minimal template under `alembic`.
- **Exclude LangGraph tables** from autogenerate via `include_object` in `env.py`.
- **PRESS hits crash (`dict` vs object)** → Added adapters to wrap/unwrap strategies for `fill_hits_for_pubmed`.
- **Windows tooling**: replaced `jq` with PowerShell `ConvertTo-Json` in examples.

---

## Frontend Status (alpha)
- Press Planner component (TSX) can call `POST /press/plan` and `/press/plan/hits`.
- For Windows, install NodeJS **outside** the Python venv and run `npm` / `npx` from the project root. Tailwind / UI deps to install:
  ```bash
  npm i framer-motion lucide-react
  npm i -D tailwindcss postcss autoprefixer
  npx tailwindcss init -p
  ```
- Set `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000` in `.env.local`.

**Dashboard idea** (already supported by API):
- Cards for `records_total`, `appraisals_total`
- Histogram of ratings; numeric stats from `summary.json`
- Paginated table using `/appraisals.page.json` with filters

---

## Suggested Next Steps (Roadmap)
### A. PRESS & Query Planning
- Add librarian‑grade PRESS checks (mapping coverage report; flag lines lacking synonyms; adjacency and phrase proximity, e.g., `"..."~5`).
- Support additional databases/interfaces (CINAHL, Embase, ERIC native) with their headings/fields.
- Auto‑limits by date/language/humans as configurable knobs.
- Multi‑DB **hit counts** (parallel queries with rate limits, cached).

### B. Retrieval & Ranking
- Deduplicate by DOI/PMID/normalized title; cluster near‑duplicates.
- Hybrid retrieval (BM25 + dense) and **re‑ranking** (cross‑encoder or LLM rerank node).
- Agentic RAG for **clarification questions** when LICO is vague.

### C. Appraisal & Rubric
- Align numeric `score_final` thresholds to R/A/G bands; keep textual rationale and citations.
- Map appraisal rubric to the **Red/Amber/Green data extraction form** fields; store extraction JSON per record.
- Add **PRESS‑to‑appraisal trace** (which line retrieved which record) for provenance.

### D. Evals & Observability
- LangSmith tracing on graph; add **eval set** for retrieval quality (precision@k, MRR) and appraisal faithfulness.
- Lightweight CI gate: run evals on PR; alert on regressions.
- Structured logs + metrics (Prometheus) for latency/tokens per node.

### E. UX
- Full Next.js app with:
  - **Run launcher** (enter free text → shows LICO helper → PRESS plan preview → run).
  - **Results browser** (filters, sort, exports; badge by label; open PubMed links).
  - **Planner worksheet** (editable lines with in‑place hit counts and diff view).

### F. Platform & Security
- API auth (basic token in dev; OIDC later), per‑tenant run isolation.
- Rate limiting; CORS restricted to known origins in non‑dev.
- Docker Compose for API + Postgres + frontend; one‑command local up.

---

## Cost & Latency Notes (MVP)
- Main costs are model tokens during retrieval/appraisal; caching and smaller models for non‑critical steps lower spend.
- Parallel source calls keep latency reasonable; re‑rank/LLM judge adds latency—consider early‑exit when confidence high.

---

## Operations Runbook (Cheat Sheet)
**Start API**
```powershell
. .\.venv\Scripts\Activate.ps1
python -m uvicorn app.server:app --reload
```
**Create run & view**
```powershell
$tid = [guid]::NewGuid().ToString()
$resp = irm "http://127.0.0.1:8000/run" -Method POST -ContentType "application/json" -Body (@{query="..."; thread_id=$tid} | ConvertTo-Json)
$RUN = $resp.run_id
irm "http://127.0.0.1:8000/runs/$RUN/summary.json" | ConvertTo-Json -Depth 5
```
**PRESS**
```powershell
$body = (@{ lico = @{ learner="..."; intervention="..."; context="..."; outcome="..." } } | ConvertTo-Json)
irm "http://127.0.0.1:8000/press/plan" -Method POST -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 8
irm "http://127.0.0.1:8000/press/plan/hits" -Method POST -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 8
```

---

## Handoff Notes for Future Engineers
- **Server**: `app/server.py` now embeds a LICO‑aware PRESS planner and adapters for hit counts.
- **DB**: Ensure `score_final` exists; run Alembic migrations and `backfill_score_final` if upgrading.
- **Autogenerate**: `env.py` excludes LangGraph tables; don’t re‑add them.
- **Windows**: Prefer `ConvertTo-Json` over `jq`; run Node outside Python venv.
- **Secrets**: Keep in `.env`; do not commit.

### Open Questions
- Desired coverage of non‑MEDLINE databases? Priority order?
- Exact thresholds mapping numeric `score_final` → R/A/G bands?
- Press limits defaults (date, language, humans) per project/team?
- How to represent extraction fields (normalized schema vs freeform JSON)?

---

## File Map (Key Pieces)
- `app/server.py` — API, exports, planner
- `app/sources.py` — source adapters
- `app/graph/build.py` — LangGraph orchestrator
- `app/persist.py` — persistence glue
- `app/db.py` — SQLAlchemy models & session
- `alembic/` — migrations (`env.py` excludes LG tables)
- `app/scripts/backfill_score_final.py` — numeric score backfill
- `app/press_contract.py` — LICO & response pydantic models
- `app/press_hits.py` — PubMed hit‑count helper
- `app/ui/PressPlanner.tsx` — (if present) frontend planner

---

## Appendix A — Example Responses
**`POST /press/plan` (body excerpt)**
```json
{
  "lico": {
    "learner": "prelicensure nursing and medical students",
    "intervention": "simulation-based active learning",
    "context": "university and clinical placements",
    "outcome": "attitudes and skills; patient outcomes if available"
  }
}
```
**Response (excerpt)** includes numbered lines (1–6), combine `1 AND 2 AND 3 AND 4`, and limits line.

**`GET /runs/{id}/appraisals.page.json`** supports:
```
?score_min=0.7&order_by=score_final&order_dir=desc
label_in=Red,Amber&label_order=Red,Amber,Green
```

---

## Appendix B — Postgres Handy Queries
```sql
-- Check columns
SELECT column_name, data_type FROM information_schema.columns WHERE table_name='appraisals';

-- Inspect some scores
SELECT rating, score_final, created_at FROM appraisals ORDER BY created_at DESC LIMIT 20;
```

---

**End of report.**

