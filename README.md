# AI MVP - Evidence Assistant

An AI-powered systematic literature review application that automates academic research workflows using the PRESS methodology and LICO framework.

## 🔬 Overview

The Evidence Assistant streamlines systematic literature reviews through a 5-step automated pipeline:

1. **PRESS Planning** - Generate systematic search strategies using the PRESS framework
2. **Harvesting** - Search 6 academic databases (PubMed, Crossref, arXiv, ERIC, Semantic Scholar, Google Scholar)
3. **Deduplication & Screening** - Fuzzy deduplication (96% threshold) + inclusion/exclusion screening
4. **Quality Appraisal** - Rubric-based assessment with 8 weighted criteria
5. **PRISMA Reporting** - Generate standardized flow diagrams and statistics

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** with pip
- **Node.js 16+** with npm
- **Git** for version control

### Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jermn007/ai-mvp---Evidence-Assistant.git
   cd ai-mvp
   ```

2. **Create environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Add required API keys to `.env`:**
   ```env
   OPENAI_API_KEY=your_openai_key_here
   LANGSMITH_API_KEY=your_langsmith_key_here
   SERPAPI_API_KEY=your_serpapi_key_here
   S2_API_KEY=your_semantic_scholar_key_here
   ```

### Backend Setup (FastAPI)

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize database:**
   ```bash
   alembic upgrade head
   ```

3. **Start the backend server:**
   ```bash
   uvicorn app.server:app --reload --port 8000
   ```

   Backend will be available at: `http://localhost:8000`

### Frontend Setup (React/TypeScript)

1. **Navigate to frontend directory:**
   ```bash
   cd frontend/press-planner
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start development server:**
   ```bash
   npm run dev
   ```

   Frontend will be available at: `http://localhost:5173`

## 📋 Usage

### Starting a Literature Review

1. **Access the web interface** at `http://localhost:5173`
2. **Choose your approach:**
   - **LICO Components**: Define Learner, Intervention, Context, Outcome
   - **Research Question**: Write your complete research question
3. **Configure settings:**
   - Select template (Education, Clinical, General)
   - Enable/disable stock scaffolds
   - Toggle AI assistance
4. **Build PRESS Plan** and execute the workflow

### LICO Search Terms Preview

- Fill in LICO components to see how your terms integrate with search strategies
- Preview shows user-extracted terms merged with template terms
- Real-time feedback on search strategy effectiveness

### Export Options

- **CSV Export**: Records, appraisals, and screening decisions
- **JSON Export**: Complete structured data
- **PRISMA Flow**: Visual diagram and statistics

## 🛠️ Development Commands

### Backend Commands

```bash
# Run local workflow (no API server)
python app/run_local.py

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Run tests
pytest tests/

# Database inspection
python app/peek_db.py
```

### Frontend Commands

```bash
cd frontend/press-planner

# Development
npm run dev

# Production build
npm run build

# Linting
npm run lint

# Type checking
npx tsc --noEmit
```

## 🏗️ Architecture

### Core Technologies

- **Backend**: FastAPI, SQLAlchemy, LangGraph, Pydantic
- **Frontend**: React, TypeScript, Vite
- **Database**: PostgreSQL (preferred) or SQLite (fallback)
- **AI/ML**: OpenAI GPT, LangSmith for monitoring

### Key Components

- **`app/server.py`** - FastAPI application with 15+ endpoints
- **`app/models.py`** - Pydantic models for API contracts
- **`app/db.py`** - SQLAlchemy database models
- **`app/sources.py`** - Academic database integrations
- **`app/graph/`** - LangGraph workflow orchestration
- **`frontend/src/`** - React components and services

### Database Schema

- **SearchRun** - Main execution container
- **Record** - Individual research papers
- **Appraisal** - Quality ratings with scores
- **Screening** - Include/exclude decisions
- **PrismaCounts** - PRISMA flow statistics

## 🔧 Configuration

### Key Configuration Files

- **`config/rubric.yaml`** - Quality assessment scoring weights
- **`config/press_terms.yaml`** - MeSH terms and search patterns
- **`app/press_templates/*.yaml`** - Domain-specific PRESS templates

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for AI features | Yes |
| `LANGSMITH_API_KEY` | LangSmith for AI monitoring | No |
| `SERPAPI_KEY` | Google Scholar via SerpAPI | No |
| `S2_API_KEY` | Semantic Scholar API | No |
| `CROSSREF_MAILTO` | Contact email for Crossref/NCBI politeness headers | No |
| `DATABASE_URL` | Database connection string | No |

## 🧪 API Endpoints

### Core Endpoints

- **`POST /run`** - Execute complete research workflow
- **`POST /run/press`** - Execute with PRESS plan
- **`POST /press/plan/queries`** - Generate search queries
- **`POST /press/plan/preview`** - Preview LICO term integration
- **`GET /runs/{run_id}/export/{format}`** - Export results

### Health & Status

- **`GET /health`** - System health check
- **`GET /ai/status`** - AI service availability
- **`GET /sources/test`** - Database connection test

## 🔍 Recent Updates

### Latest Features (v1.2.0)

- ✅ **LICO Search Terms Preview** - Real-time preview of search term integration
- ✅ **Fixed API Connectivity** - Resolved port configuration issues
- ✅ **Export File Extensions** - CSV files now download with proper extensions
- ✅ **Institution Metadata** - Author affiliation extraction and display

### Performance Improvements

- Optimized SQLite configuration with WAL mode
- Enhanced error handling and logging
- Improved frontend state management
- Better API response caching

## 🐛 Troubleshooting

### Common Issues

1. **Search Terms Preview shows 404 error**
   - Ensure backend is running on port 8000
   - Check API connectivity in browser network tab

2. **Export files have no extension**
   - Update to latest version (fixed in v1.2.0)
   - Check Content-Disposition headers

3. **Database errors**
   - Run `alembic upgrade head` to apply migrations
   - Check SQLite file permissions

4. **Missing API responses**
   - Verify API keys in `.env` file
   - Check rate limits on external services

### Support

For issues and feature requests, please check:
- [GitHub Issues](https://github.com/jermn007/ai-mvp---Evidence-Assistant/issues)
- [CLAUDE.md](./CLAUDE.md) for development guidance

## Known Issues & Limitations

### Search Sources

- **Silent source skipping** — If an API key is missing or a source returns an error, that source is silently excluded from results rather than raising an error. If your result counts seem low, check that all keys in `.env` are set and valid.
- **Results capped at 25 per source** — The default `max_results_per_source` is 25. Change this in `config.yaml` under `search.modes` for more comprehensive sweeps (note: higher limits increase runtime significantly).
- **Semantic Scholar rate limits** — Without an `S2_API_KEY`, anonymous requests are heavily rate-limited. Set the key for reliable access.

### Deduplication

- **Title-only deduplication** — By default, deduplication uses title fuzzy-matching (96% threshold) and exact DOI/ID matching only. Abstract and author similarity checks are available in `config.yaml` but disabled by default, so papers with different titles but identical content may slip through.

### Database

- **SQLite schema migrations** — The app includes a runtime compatibility shim that patches missing columns on startup. If you encounter `table X has no column named Y` errors on an existing database, run `alembic upgrade head` (back up `app.db` first).
- **PostgreSQL checkpointer warning** — When running with SQLite, you may see a noisy `PostgresSaver` initialization warning in the logs. This is harmless and does not affect functionality.

### Optional Dependencies

- **PDF text extraction disabled without PyPDF2** — Full-text retrieval from PDFs requires `PyPDF2`. If it is not installed, PDF processing is silently skipped. Install it with `pip install PyPDF2`.
- **Retry logic disabled without tenacity** — LLM call retries require the `tenacity` package. All packages are included in `requirements.txt`; this only affects custom installs that skip the full requirements.

### LangChain Warnings

- **Deprecation warnings** — LangChain versions ship with numerous deprecation warnings. These are suppressed in tests but may appear at runtime. They do not affect functionality with the current pinned versions in `requirements.txt`.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

Built with ❤️ for systematic literature review automation