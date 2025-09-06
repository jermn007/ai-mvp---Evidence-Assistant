# Evidence Assistant (MVP) — Build Report & Handoff (2025‑09‑05)

## Executive Summary
We implemented flexible, PRESS‑aligned planning with selectable templates (education, clinical, general), LICO merge, query previews, and a UI line editor. Runs can be launched directly from an approved plan. Exports and the dashboard were expanded to support PRISMA reasoning, included/excluded views, and richer filters. Persistence and sources were stabilized (score_final, screenings, arXiv, GoogleScholar naming).

## Key Changes Today
- Rubric + scoring
  - Backward‑compatible rubric loader that supports both schemas; persist `score_final` for new runs.
  - Files: `app/rubric.py`, `app/persist.py`
- PRESS planning
  - Template‑driven planner (YAML): education, clinical, general; `use_stock` toggle to include/exclude template scaffolds; years/limits handling.
  - Derive queries without running (`POST /press/plan/queries`).
  - Run directly from plan (`POST /run/press`), preserving the plan in state; harvest respects plan `sources`.
  - Files: `app/server.py`, `app/press_templates/*.yaml`
- Exports & PRISMA
  - Records + appraisals: CSV/JSON and paged JSON with filters.
  - Screenings + records (deduped items with reasons): CSV/JSON and paged JSON with filters.
  - PRISMA summary: JSON/CSV with reason aggregation.
  - Files: `app/server.py`
- Dashboard (Streamlit)
  - Plan & Run expander: template selector (education/clinical/general), `use_stock` toggle, Build Plan → (optional) PubMed hits → Run with Plan.
  - Line editor: editable MEDLINE lines table (add/edit/delete), apply/reset; query previews (PubMed + generic).
  - Records view: toggle Included/Excluded with paging and filters; PRISMA “exclusion reasons” chart; download snippets.
  - File: `app/ui/dashboard.py`
- Connectors & stability
  - arXiv via HTTPS + redirects; GoogleScholar label normalization across API/exports.
  - Harvest respects `press.sources` (limit to selected providers per run).
  - Files: `app/sources.py`, `app/graph/nodes.py`

## New / Updated Endpoints
- Planning
  - `POST /press/plan` (body: `lico`, `template`, `use_stock`, optional `databases`)
  - `POST /press/plan/hits` (as above, adds PubMed line counts)
  - `POST /press/plan/queries` → `{ query_pubmed, query_generic, years }`
  - `GET /runs/{id}/press.plan(.hits).json`
- Running
  - `POST /run` (supports either `query` or `lico` with optional `years`, `sources`)
  - `POST /run/press` (body: `plan`, optional `sources`, `thread_id`)
- Exports
  - Records: `/runs/{id}/records.(json|csv)`, `/records_with_appraisals.(json|csv)`, `/records_with_appraisals.page.json`
  - Screenings: `/runs/{id}/screenings_with_records.(json|csv)`, `/screenings_with_records.page.json`
  - PRISMA: `/runs/{id}/prisma.summary.(json|csv)`
  - Runs list: `/runs.page.json`, Run summary: `/runs/{id}/summary.json`

## Dashboard Updates (How to Use)
- Plan & Run
  - Choose Template (education/clinical/general) and toggle `Use stock scaffolds`.
  - Enter LICO; Build Plan → (optional) Add PubMed Hits → edit lines → review derived queries → Run with Plan.
- Records
  - Switch between Included (appraised) and Excluded (screened) with paging + filters for labels/score/sources/year/search (included) and reasons/sources/year/search (excluded).
  - PRISMA reasons chart; download CSVs.

## Persistence & Integrity
- Screenings: always persisted (including excluded items) by creating minimal placeholder `Record` rows for deduped‑but‑excluded items to satisfy FK constraints.
- `score_final`: stored for new appraisals; backfill script included for older runs.

## Operational Notes
- `.env` must use plain `KEY=VALUE` lines (e.g., `DATABASE_URL=postgresql+psycopg2://…`). Do not use PowerShell `$env:` syntax in `.env`.
- arXiv: switched to `https://export.arxiv.org` and enabled HTTP redirect following.
- Source naming: `Scholar` is normalized to `GoogleScholar` at API/read/export layers for consistency.

## Quick Validation
- API health: `GET /health` and `/health/checkpointer`.
- Sources smoke: `GET /sources/test?q=active learning in higher education&max_n=5`.
- Planning (PowerShell):
  - `$body = @{ lico=@{ learner=""; intervention="eHealth app"; context=""; outcome="behavior change" }; template="clinical"; use_stock=$true } | ConvertTo-Json`
  - `$plan = irm "http://127.0.0.1:8000/press/plan" -Method POST -ContentType "application/json" -Body $body`
  - `irm "http://127.0.0.1:8000/press/plan/queries" -Method POST -ContentType "application/json" -Body (@{ plan=$plan } | ConvertTo-Json -Depth 10)`
- Run with plan:
  - `$req = @{ plan=$plan; sources=@("PubMed","ERIC","Crossref","SemanticScholar","GoogleScholar","arXiv") } | ConvertTo-Json -Depth 10`
  - `irm "http://127.0.0.1:8000/run/press" -Method POST -ContentType "application/json" -Body $req`
- Inspect results:
  - `GET /runs/{RUN}/summary.json`, `/records_with_appraisals.page.json`, `/screenings_with_records.page.json`, `/prisma.summary.csv`
- Dashboard: `streamlit run app/ui/dashboard.py`

## Known Notes / Constraints
- StrategyLine.type is constrained; non‑standard facet names (e.g., Condition, StudyDesign) are returned as type `Text` to satisfy schema.
- Planner skips empty facet lines and renumbers; Combine references only kept lines (prevents leading empty parentheses in queries).
- Query derivation and “Run with Plan” use exactly the edited lines displayed in the dashboard.

## Next Steps (Recommended)
1. Assistant stepper (Phase 1 flow)
   - Approve plan → run one source at a time → review results → next source.
   - Dashboard: “Run this source next” buttons and per‑source results view.
2. Provenance
   - Add `record.provenance_json` capturing source, query used, and (optionally) contributing plan lines; show in UI row expand.
3. Screening criteria
   - Expand beyond `Pre‑2018` (population, design, context); UI selectors; charts.
4. Observability
   - Persist per‑node timings; display in run summary and charts; optional LangSmith tracing.
5. Planner polish
   - Optional synonym suggestions per facet (LLM‑assisted) with user approval.
   - Editable template content (advanced), and guardrails for Combine/Limits.

## File Map (Touched)
- Planner & API: `app/server.py`, `app/press_templates/education.yaml`, `app/press_templates/clinical.yaml`, `app/press_templates/general.yaml`
- Dashboard: `app/ui/dashboard.py`
- Graph & scoring: `app/graph/nodes.py`, `app/rubric.py`, `app/persist.py`
- Sources: `app/sources.py`

---
Prepared by Codex on 2025‑09‑05. Next session proposal: implement the per‑source stepper (Phase 1) or add provenance on records; your call on priority.
