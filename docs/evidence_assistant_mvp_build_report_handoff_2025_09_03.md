# Evidence Assistant (MVP) — Build Report & Handoff
_Date: 2025‑09‑03_

## Executive summary
You’re building a multi‑agent tool to help instructional designers **find, appraise, and report evidence**. The current MVP runs as a LangGraph pipeline with nodes that: (1) plan a PRESS‑style search, (2) harvest across multiple scholarly sources, (3) dedupe & screen, (4) appraise with a Red/Amber/Green rubric, and (5) report PRISMA counts—**persisting every record & appraisal** to a database. A FastAPI server exposes a `/run` endpoint; a CLI runner and a `peek_db` utility help with local testing and inspection. Observability is in place: per‑source counts and per‑node timings.

---

## What works now
- **Graph & state (LangGraph):** `plan_press → harvest → dedupe_screen → appraise → report_prisma`.
- **Sources:** PubMed, Crossref, arXiv, ERIC, Semantic Scholar (Graph API via `x-api-key`), Google Scholar (via SerpAPI).
- **Observability:** `source_counts` by provider; `timings` per node; INFO logs.
- **Persistence:** SQLite by default; Postgres optional. Records, appraisals, and PRISMA counts saved per run.
- **API:** `POST /run` triggers a search & appraisal; `/health` and `/health/checkpointer` endpoints.
- **CLI:** `python -m app.run_local` for one‑shot runs; `python -m app.peek_db` to inspect last runs.
- **Safety & resilience:** Robust checkpointer init (Postgres context manager vs object), fallback to memory; duplicate handling for re‑runs; year filtering and thread‑level dedupe via `seen_external_ids`.

---

## Architecture overview
**Runtime:** Python 3.12, LangChain ≥0.3, LangGraph ≥0.2, FastAPI, SQLAlchemy.

**Flow:**
1. **plan_press** — Creates a `PressPlan` from the user query (concepts, boolean string, year range, source list). Initializes PRISMA counters, thread memory, and run_id.
2. **harvest** — Asynchronously queries all configured sources (25 max each), collects results, tracks **per‑source counts**, applies thread‑memory and year filters, validates to `RecordModel`.
3. **dedupe_screen** — Title‑similarity & key‑based dedupe (RapidFuzz); simple screening rule (e.g., pre‑2018 exclusion). Updates PRISMA (deduped/screened/excluded/eligible).
4. **appraise** — Applies **rubric.yaml** to assign R/A/G with component scores & rationale. Updates PRISMA (included).
5. **report_prisma** — Updates thread memory with kept external IDs for future runs.
6. **persist** — Writes `SearchRun`, `Record`, `Appraisal`, `PrismaCounts` rows.

**Checkpointer:**
- Prefers **PostgresSaver** if `DATABASE_URL` is present; otherwise **MemorySaver**.
- Handles both “returns‑object” and “context‑manager” APIs via a wrapper.

**Server:** FastAPI app exposes `/run`, health endpoints; permissive CORS for local/dev.

---

## Repository layout (key files)
```
app/
  graph/
    build.py          # compiles graph; checkpointer init & fallback
    nodes.py          # plan_press, harvest, dedupe_screen, appraise, report_prisma
    state.py          # AgentState (incl. source_counts, timings)
  sources.py          # PubMed, Crossref, arXiv, ERIC, S2, SerpAPI connectors
  models.py           # Pydantic models: PressPlan, RecordModel, ScreeningModel, AppraisalModel, PrismaCountsModel
  rubric.py           # Rubric loader + scoring logic (R/A/G)
  db.py               # SQLAlchemy engine/session/models
  persist.py          # persist_run(final) writes SearchRun/Record/Appraisal/PrismaCounts
  peek_db.py          # inspect the last N runs from the DB
  run_local.py        # CLI one-shot runner
  server.py           # FastAPI app (POST /run, /health, /health/checkpointer)
.env                  # API keys and config (not committed)
rubric.yaml           # R/A/G weights and thresholds
requirements.txt      # pinned runtime deps
```

---

## Environment & configuration
**Python:** 3.12

**Core dependencies:**
- `langgraph` (≥0.2.x), `langchain` (≥0.3.x)
- `fastapi`, `uvicorn[standard]`
- `sqlalchemy`, `pydantic` (v2), `python-dotenv`
- `httpx` (async HTTP), `rapidfuzz` (dedupe)
- Optional: `psycopg[binary]` when using Postgres checkpointer/DB

**.env variables (sample):**
```
OPENAI_API_KEY=sk-...
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=ai-mvp-dev
LANGCHAIN_TRACING_V2=true
CROSSREF_MAILTO=you@example.com

# Retrieval sources
S2_API_KEY=...              # Semantic Scholar Graph API
SERPAPI_KEY=...             # SerpAPI for Google Scholar
ERIC_API_BASE=https://api.ies.ed.gov/eric/  # optional; leave unset to use default

# Graph checkpointing / database
DATABASE_URL=postgresql+psycopg2://languser:changeme@localhost:5432/langgraph
LOG_LEVEL=INFO
```
> The graph will **strip** `+psycopg2` for the PostgresSaver URL automatically. If `DATABASE_URL` is missing or Postgres init fails, it falls back to **in‑memory** checkpoints.

---

## How to run locally
**1) CLI one‑shot run**
```powershell
# From project root (venv active)
python -m app.run_local
```
Expected console output includes PRISMA counts and a summary of appraisals. The run is persisted; see `app.peek_db` below.

**2) API server**
```powershell
python -m uvicorn app.server:app --reload
```
Endpoints:
- `POST /run` — body: `{ "query": "...", "thread_id": "optional-guid" }`
- `GET /health` — basic ok + env presence
- `GET /health/checkpointer` — `{"checkpointer": "postgres"|"memory"}`

**3) Inspect the DB**
```powershell
python -m app.peek_db
```
Shows the last runs, a sample of records, per‑source counts (if patch applied), appraisals, and PRISMA totals.

---

## Data model (SQLAlchemy)
- **SearchRun**: `id` (UUID), `query`, `created_at`.
- **Record**: `id` (composite strategy: `run_id:external_id`), `run_id`, `title`, `abstract`, `year`, `doi`, `url`, `source`, `created_at`.
  - This avoids UNIQUE constraint clashes when the same external ID appears across multiple runs.
- **Appraisal**: `id`, `run_id`, `record_id`, `rating` (R/A/G), `scores` (JSON), `rationale`, `citations` (JSON), `created_at`.
- **PrismaCounts**: `run_id` (PK, FK), `identified`, `deduped`, `screened`, `excluded`, `eligible`, `included`.

Duplicate insert protection and idempotency have been addressed in `persist.py` by using composite record IDs per run and handling existing rows gracefully.

---

## Graph state (Pydantic + TypedDict)
`AgentState` fields currently include:
- `run_id: str`
- `query: str`
- `press: PressPlan` (concepts, boolean, sources, years like `"2019-"`)
- `records: List[RecordModel]`
- `screenings: List[ScreeningModel]`
- `appraisals: List[AppraisalModel]`
- `prisma: PrismaCountsModel`
- `seen_external_ids: List[str]` (thread‑level memory across runs)
- `source_counts: Dict[str, int]` (per‑source, pre‑filter)
- `timings: Dict[str, float]` (seconds per node)

---

## Source connectors (harvest)
**Providers & notes:**
- **PubMed (NCBI E-utilities)** — `esearch` + `esummary`.
- **Crossref** — `works` endpoint; set `CROSSREF_MAILTO`.
- **arXiv** — Atom API (HTTPS endpoint used to avoid 301).
- **ERIC** — default `api.ies.ed.gov/eric/` (configurable via `ERIC_API_BASE`).
- **Semantic Scholar (Graph API)** — `x-api-key` header; fields: `title,year,abstract,externalIds,url`.
- **Google Scholar via SerpAPI** — query param `api_key`; passes `as_ylo` when PRESS years like `2019-`.

**Filtering & dedupe:**
- Thread memory: remove already‑seen external IDs (`record_id`).
- Year floor: parse `press.years` (e.g., `2019-`).
- Title dedupe: RapidFuzz `token_set_ratio ≥ 96` + DOI/external key collapse.

**Observability:**
- `source_counts` is captured **before** filtering (per‑provider identified counts).
- INFO logs print `per_source`, `kept`, and `identified` totals.

---

## Appraisal (R/A/G)
- **Config:** `rubric.yaml` — weights for `recency`, `design`, `bias` (example), thresholds to map final score → Red/Amber/Green.
- **Output:** `AppraisalModel` with `rating`, `scores` (per‑dimension, float), `rationale` (ties back to rubric), `citations` (e.g., record URL or DOI).
- **Calibration (planned):** will import a gold CSV (record_id,gold_label) and compute confusion matrix and metrics; no‑code sheet support planned.

---

## Observability
- **Per‑source counts:** `state["source_counts"]` (e.g., `{PubMed: 25, Crossref: 25, ERIC: 25, SemanticScholar: 25, Scholar: 20}`)
- **Per‑node timings:** `state["timings"]` with seconds for `plan_press`, `harvest`, `dedupe_screen`, `appraise`, `report_prisma`.
- **Health endpoints:** `/health`, `/health/checkpointer`.
- **DB inspection:** `peek_db` prints by‑source summary and appraisals for the newest run.

---

## Example run (recent)
- **Log excerpt:** `harvest: per_source={PubMed: 25, Crossref: 25, ERIC: 25, SemanticScholar: 25, Scholar: 20} kept=34 identified=120`
- **PRISMA (example):** `identified=120, deduped≈28–35, screened≈deduped, excluded≈0–few (rule‑based), eligible≈kept, included≈appraised`
- **API response fields:** `thread_id, run_id, prisma, n_appraised, ratings[], source_counts{}, timings{}`
- **DB:** records persisted with `run_id:external_id` composite key; appraisals & PRISMA stored.

---

## Troubleshooting log (greatest hits)
- **PowerShell parsing (`&&`, heredoc, spaces in paths):** Use PowerShell‑friendly syntax; quote paths with spaces.
- **Execution policy blocks venv activation:** `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (then `.\.venv\Scripts\Activate.ps1`).
- **`ModuleNotFoundError: app` when running files directly:** Use module mode: `python -m app.run_local`.
- **LangGraph `config_schema` / version skew:** Upgraded LangGraph; removed/updated params accordingly.
- **Checkpointer API mismatch (context manager vs object):** Wrapped `PostgresSaver.from_conn_string` to handle both; registered `atexit` to close.
- **`.env` parse errors / missing env in shell:** Ensure valid `KEY=VALUE` lines; call `load_dotenv()` early in `run_local.py` and `server.py`.
- **SQLite UNIQUE constraint (records.id):** Switched to per‑run composite `record_id` (`run_id:external_id`) to avoid clashes.
- **`DATABASE_URL` not injected in shell tests:** Use `load_dotenv()` in quick Python one‑liners or set `$Env:DATABASE_URL`.
- **arXiv 301 spam:** Switched to HTTPS base URL.

---

## Deployment notes (Docker/VM)
- The app is **12‑factor friendly**: all secrets via env; stateless API; durable DB & checkpointing as services.
- **Dockerfile/compose** can mount a persistent volume for the DB (or point to managed Postgres).
- For NAS‑backed NFS volumes, create a named volume (e.g., `aimvp_data`) and use `driver_opts` as in your Home Assistant setup.
- Health endpoints and a `/sources/test` route (optional) make smoke checks easy in containerized environments.

---

## Next steps (prioritized)
**Now (MVP hardening)**
1. **Retries & backoff** for HTTP connectors (tenacity or custom) + timeouts per source.
2. **/sources/test** endpoint to verify each provider (counts, error) from the browser.
3. **Export endpoints**: `/runs/{run_id}/records(.json|.csv)`, `/runs/{run_id}/appraisals(.json|.csv)`, `/runs/{run_id}/summary`.
4. **PRISMA diagram export** (JSON + PNG/SVG) for reports.
5. **Postgres by default** in dev/prod; keep SQLite for local quickstarts.

**Next (quality & UX)**
6. **Appraisal calibration**: no‑code gold CSV import; compute confusion matrix, accuracy, macro‑F1; per‑class precision/recall; threshold sweeps from `rubric.yaml`.
7. **Re‑ranking & compression**: MMR/HYDE or Cross‑encoder re‑ranker before appraise; optional dedupe threshold tuning.
8. **Cost/latency controls**: caps per source, early‑stop when enough high‑confidence items; caching for repeat queries.
9. **Basic UI** (FastAPI + HTMX or small React page): show PRISMA, counts, filters, download buttons.

**Later (agents & robustness)**
10. **Assistant specialization**: Split nodes into distinct assistants (PRESS planner, harvester, appraiser, reporter) with clearer prompts & guardrails.
11. **LangSmith evals**: task runs and RAG evals (if added) with dashboards.
12. **Observability**: structured logs, request IDs, and optional metrics (Prometheus) + alerts.
13. **Security**: key rotation guidance; PII‑aware logging; rate limiting.

---

## API reference (current)
**POST `/run`**
- Request: `{ "query": "string", "thread_id": "optional-guid" }`
- Response:
  ```json
  {
    "thread_id": "...",
    "run_id": "...",
    "prisma": {"identified": n, "deduped": n, "screened": n, "excluded": n, "eligible": n, "included": n},
    "n_appraised": n,
    "ratings": ["Green"|"Amber"|"Red", ...],
    "source_counts": {"PubMed": n, "Crossref": n, ...},
    "timings": {"plan_press": s, "harvest": s, ...}
  }
  ```

**GET `/health`** → `{ "ok": true, "env": true|false }`

**GET `/health/checkpointer`** → `{ "checkpointer": "postgres"|"memory" }`

(Planned) **GET `/sources/test`** → `{ source: {count, error?}, ... }`

---

## Appendix A — `rubric.yaml` (example scaffold)
```yaml
weights:
  recency: 0.4
  design:  0.35
  bias:    0.25
thresholds:
  green: 0.75
  amber: 0.60
# Any other dimensions you add should be handled in app.rubric
```

## Appendix B — PRESS plan structure
```yaml
concepts: ["<user-query>"]
boolean:  "(\"<user-query>\"[Title/Abstract]) AND (study OR trial OR evaluation)"
sources:  ["PubMed", "Crossref", "arXiv", "ERIC", "SemanticScholar", "Scholar"]
years:    "2019-"
```

## Appendix C — Common one‑liners (PowerShell)
```powershell
# Activate venv
. .\.venv\Scripts\Activate.ps1

# Run once
python -m app.run_local

# Start API
python -m uvicorn app.server:app --reload

# Invoke (new thread id)
$tid = [guid]::NewGuid().ToString()
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/run" `
  -ContentType "application/json" `
  -Body (@{ query="active learning in higher education"; thread_id=$tid } | ConvertTo-Json) | ConvertTo-Json

# Inspect DB
python -m app.peek_db
```

---

### Final notes
- Keys live in `.env`; don’t commit them. In CI/CD, inject via secrets.
- If a source shows `0` in `source_counts`, check keys, year filter, and dedupe/thread memory effects.
- For production, prefer managed Postgres for both **DB** and **LangGraph checkpointer**.

