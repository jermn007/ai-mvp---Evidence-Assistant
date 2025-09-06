# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered systematic literature review application that automates academic research workflows. It uses LangGraph to orchestrate a 5-step process: PRESS planning → harvesting → deduplication/screening → appraisal → PRISMA reporting.

## Development Commands

### Backend (Python/FastAPI)
```bash
# Install dependencies
pip install -r requirements.txt

# Run local workflow (no API server)
python app/run_local.py

# Run FastAPI server
uvicorn app.server:app --reload

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend (React/TypeScript)
```bash
cd frontend/press-planner
npm install
npm run dev          # Development server
npm run build        # Production build
npm run lint         # ESLint
```

### Environment Setup
- Copy `.env` with required API keys: `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, `SERPAPI_API_KEY`, `S2_API_KEY`
- Database: PostgreSQL preferred, SQLite fallback configured via `DATABASE_URL`

## Architecture Overview

### Core Workflow (LangGraph)
Sequential 5-node pipeline in `app/graph/`:
1. **plan_press** - Generate PRESS search strategy 
2. **harvest** - Search 6 academic databases (PubMed, Crossref, arXiv, ERIC, Semantic Scholar, Google Scholar)
3. **dedupe_screen** - Fuzzy deduplication (96% threshold) + inclusion/exclusion screening
4. **appraise** - Rubric-based quality scoring with 8 weighted criteria
5. **report_prisma** - Generate PRISMA flow statistics

### Key Modules
- `app/server.py` - FastAPI application with 15+ endpoints
- `app/models.py` - Pydantic models for API contracts
- `app/db.py` - SQLAlchemy models (SearchRun, Record, Appraisal, Screening)
- `app/sources.py` - Academic database search integrations
- `app/rubric.py` - Quality assessment scoring system
- `app/press*.py` - PRESS planning system and query generation

### Database Models
- **SearchRun** - Main execution container
- **Record** - Individual research papers 
- **Appraisal** - Quality ratings (Red/Amber/Green) with scores
- **Screening** - Include/exclude decisions
- **PrismaCounts** - PRISMA flow statistics

### Configuration Files
- `rubric.yaml` - Scoring weights and thresholds for quality assessment
- `config/press_terms.yaml` - MeSH terms and text patterns for search expansion
- `app/press_templates/*.yaml` - Domain-specific PRESS planning templates

## API Endpoints
- `POST /run` - Execute complete research workflow
- `POST /run/press` - Execute with PRESS plan
- `POST /press/plan/queries` - Generate search queries from concepts
- `GET /runs/{run_id}/export/{format}` - Export results (JSON/CSV)
- `GET /sources/test` - Test academic database connections

## Testing & Utilities
- `app/scripts/smoke_api.ps1` - API testing script
- `app/scripts/test_rubric_loader.py` - Validate rubric configuration
- `app/peek_db.py` - Database inspection utility
- `app/export.py` - Data export functionality

## Development Notes

### Source Integrations
Each academic database has async search functions with rate limiting and error handling. API keys required for Semantic Scholar and SerpAPI (Google Scholar).

### Scoring System
Uses weighted rubric with 8 criteria including design strength, bias risk, Kirkpatrick levels, and recency. Scores normalized to 0-1 with color thresholds.

### PRESS Planning
Systematic search strategy development using concept expansion, boolean logic, and source selection. Templates available for clinical, education, and general domains.