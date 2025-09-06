# Evidence Assistant MVP - Quick Start Guide

## Prerequisites
- Docker (for PostgreSQL)
- Python 3.11+
- Environment variables configured (.env file)

## Database Setup
# Start PostgreSQL container
docker run --name langgraph-postgres -e POSTGRES_USER=languser -e POSTGRES_PASSWORD=changeme -e POSTGRES_DB=langgraph -p 5432:5432 -d postgres:15

# Run migrations
python -m alembic upgrade head

# Verify database
python -m app.peek_db

## Local Development

### One-shot CLI run
python -m app.run_local

### API Server
python -m uvicorn app.server:app --reload

### Streamlit Dashboard
python -m streamlit run app/ui/dashboard.py --server.port 8501

## API Usage Examples

### Basic Evidence Search
$tid = [guid]::NewGuid().ToString()
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/run" `
  -ContentType "application/json" `
  -Body (@{ query="instructional design evidence synthesis"; thread_id=$tid } | ConvertTo-Json) | ConvertTo-Json

### PRESS Planning (Education Domain)
Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/press/plan" `
  -ContentType "application/json" `
  -Body (@{ query="active learning effectiveness"; domain="education" } | ConvertTo-Json)

### Get Run Summary
Invoke-RestMethod "http://127.0.0.1:8000/runs/$tid/summary.json"

### Export Results (Combined Records + Appraisals)
Invoke-RestMethod "http://127.0.0.1:8000/runs/$tid/records_with_appraisals.csv" -OutFile "results.csv"

### PRISMA Flow Summary
Invoke-RestMethod "http://127.0.0.1:8000/runs/$tid/prisma_summary.json"

### Filter High-Quality Results
Invoke-RestMethod "http://127.0.0.1:8000/runs/$tid/appraisals.page.json?score_min=0.7&order_by=score_final&order_dir=desc&limit=10"

## Smoke Testing
.\app\scripts\smoke_api.ps1 -Run $tid

## Key Features
- Multi-source harvesting (PubMed, Crossref, ERIC, Semantic Scholar, Google Scholar, arXiv)
- PRESS methodology planning with domain templates
- Quality scoring with configurable rubrics
- PRISMA reporting standards
- Interactive Streamlit dashboard
- LangGraph workflow orchestration
- PostgreSQL persistence with SQLite fallback
