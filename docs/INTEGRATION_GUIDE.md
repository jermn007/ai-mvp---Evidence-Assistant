# Evidence Assistant Integration Guide

## Overview

This guide provides comprehensive instructions for integrating with the Evidence Assistant API, including authentication, workflow execution, data handling, and error management.

## Quick Start

### 1. Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-openai-key"
export LANGSMITH_API_KEY="your-langsmith-key"  # Optional
export SERPAPI_API_KEY="your-serpapi-key"      # Optional
export S2_API_KEY="your-semantic-scholar-key"  # Optional

# Database setup
export DATABASE_URL="postgresql://user:pass@localhost/evidence_db"
# or use SQLite fallback
export DATABASE_URL="sqlite:///./app.db"
```

### 2. Start the API Server

```bash
# Development mode with auto-reload
uvicorn app.server:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn app.server:app --host 0.0.0.0 --port 8000 --workers 4
```

### 3. Verify Installation

```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", "timestamp": "..."}

curl http://localhost:8000/sources/test
# Expected: {"status": "success", "databases_tested": 6, ...}
```

## API Integration Patterns

### A. Simple Query Workflow

The most straightforward integration for basic literature searches:

```python
import httpx
import asyncio

async def simple_search():
    async with httpx.AsyncClient() as client:
        # Execute complete workflow
        response = await client.post(
            "http://localhost:8000/run",
            json={"query": "machine learning in medical education"},
            timeout=300.0  # 5 minutes
        )

        if response.status_code == 200:
            result = response.json()
            run_id = result["run_id"]

            # Get detailed summary
            summary = await client.get(f"http://localhost:8000/runs/{run_id}/summary.json")
            return summary.json()

# Usage
result = asyncio.run(simple_search())
print(f"Found {result['counts']['included']} high-quality studies")
```

### B. LICO-Based Structured Search

For systematic reviews requiring PRESS methodology:

```python
async def lico_search():
    async with httpx.AsyncClient() as client:
        lico_data = {
            "learner": "medical students",
            "intervention": "simulation-based training",
            "context": "clinical skills education",
            "outcome": "competency improvement"
        }

        # Step 1: Generate PRESS plan
        press_response = await client.post(
            "http://localhost:8000/press/plan",
            json=lico_data
        )
        press_plan = press_response.json()

        # Step 2: Generate optimized queries
        query_response = await client.post(
            "http://localhost:8000/press/plan/queries",
            json=press_plan
        )
        queries = query_response.json()

        # Step 3: Execute workflow with PRESS plan
        workflow_response = await client.post(
            "http://localhost:8000/run/press",
            json={
                "press_plan": press_plan,
                "queries": queries
            },
            timeout=300.0
        )

        return workflow_response.json()
```

### C. AI-Enhanced Search Strategy

Leverage AI for research question refinement and strategy optimization:

```python
async def ai_enhanced_search():
    async with httpx.AsyncClient() as client:
        # Check AI availability
        ai_status = await client.get("http://localhost:8000/ai/status")
        if not ai_status.json().get("available"):
            raise Exception("AI services not available")

        # Get AI assistance for research question
        research_question = "How effective are virtual reality interventions for surgical training?"

        ai_help = await client.post(
            "http://localhost:8000/ai/research/help",
            json={"question": research_question}
        )

        enhanced_question = ai_help.json()

        # Use AI-enhanced LICO framework
        if "lico_suggestion" in enhanced_question:
            lico = enhanced_question["lico_suggestion"]
            return await lico_search_with_ai(lico)
```

## Data Export Integration

### Available Export Formats

```python
async def export_results(run_id: str):
    async with httpx.AsyncClient() as client:
        exports = {}

        # JSON exports (structured data)
        exports["records"] = await client.get(f"http://localhost:8000/runs/{run_id}/export/records.json")
        exports["appraisals"] = await client.get(f"http://localhost:8000/runs/{run_id}/export/appraisals.json")
        exports["prisma"] = await client.get(f"http://localhost:8000/runs/{run_id}/export/prisma.json")

        # CSV exports (tabular data)
        exports["records_csv"] = await client.get(f"http://localhost:8000/runs/{run_id}/export/records.csv")
        exports["summary_csv"] = await client.get(f"http://localhost:8000/runs/{run_id}/export/summary.csv")

        return exports
```

### Working with Results

```python
def analyze_results(summary_data):
    """Process exported results for analysis"""
    counts = summary_data["counts"]

    # PRISMA flow statistics
    identification_rate = counts["identified"]
    deduplication_rate = (counts["identified"] - counts["deduped"]) / counts["identified"]
    inclusion_rate = counts["included"] / counts["eligible"] if counts["eligible"] > 0 else 0

    # Quality distribution
    quality_labels = summary_data["label_counts"]
    high_quality = quality_labels.get("Green", 0)
    moderate_quality = quality_labels.get("Amber", 0)
    low_quality = quality_labels.get("Red", 0)

    return {
        "identification_rate": identification_rate,
        "deduplication_rate": deduplication_rate,
        "inclusion_rate": inclusion_rate,
        "quality_distribution": {
            "high": high_quality,
            "moderate": moderate_quality,
            "low": low_quality
        }
    }
```

## Error Handling & Recovery

### Robust Error Handling Pattern

```python
import time
from typing import Optional

async def robust_workflow_execution(
    query_data: dict,
    max_retries: int = 3,
    timeout: float = 300.0
) -> Optional[dict]:
    """Execute workflow with comprehensive error handling"""

    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    "http://localhost:8000/run",
                    json=query_data,
                    timeout=timeout
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 422:
                    # Validation error - don't retry
                    error_detail = response.json().get("detail", "Validation failed")
                    raise ValueError(f"Invalid request: {error_detail}")
                elif response.status_code >= 500:
                    # Server error - retry with backoff
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        print(f"Server error, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Server error after {max_retries} attempts")

            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    print(f"Timeout, retrying with extended timeout...")
                    timeout *= 1.5  # Increase timeout for retry
                    continue
                else:
                    raise Exception("Workflow timeout after maximum retries")

            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    print(f"Connection error, retrying...")
                    time.sleep(2)
                    continue
                else:
                    raise Exception(f"Connection failed: {e}")

    return None
```

### Monitoring Progress

```python
async def monitor_workflow_progress(run_id: str):
    """Monitor long-running workflows"""
    async with httpx.AsyncClient() as client:
        while True:
            try:
                status = await client.get(f"http://localhost:8000/runs/{run_id}/status")
                if status.status_code == 200:
                    data = status.json()
                    print(f"Status: {data.get('status', 'unknown')}")

                    if data.get("status") in ["completed", "failed", "error"]:
                        break

                elif status.status_code == 404:
                    print("Run not found - may have completed")
                    break

                await asyncio.sleep(5)  # Check every 5 seconds

            except Exception as e:
                print(f"Error checking status: {e}")
                await asyncio.sleep(10)
```

## Performance Optimization

### Concurrent Processing

```python
async def process_multiple_queries(queries: list[str]):
    """Process multiple queries concurrently"""
    async with httpx.AsyncClient() as client:
        tasks = []

        for query in queries:
            task = client.post(
                "http://localhost:8000/run",
                json={"query": query},
                timeout=300.0
            )
            tasks.append(task)

        # Execute all queries concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                results.append({"query": queries[i], "error": str(response)})
            elif response.status_code == 200:
                results.append({"query": queries[i], "result": response.json()})
            else:
                results.append({"query": queries[i], "error": f"HTTP {response.status_code}"})

        return results
```

### Caching Strategy

```python
import hashlib
import json
from typing import Dict, Any

class ResultsCache:
    def __init__(self):
        self.cache: Dict[str, Any] = {}

    def _get_cache_key(self, query_data: dict) -> str:
        """Generate cache key from query parameters"""
        canonical = json.dumps(query_data, sort_keys=True)
        return hashlib.md5(canonical.encode()).hexdigest()

    async def get_or_execute(self, query_data: dict) -> dict:
        """Get cached result or execute new query"""
        cache_key = self._get_cache_key(query_data)

        if cache_key in self.cache:
            print(f"Cache hit for query: {query_data.get('query', 'N/A')}")
            return self.cache[cache_key]

        # Execute new query
        result = await robust_workflow_execution(query_data)

        if result:
            self.cache[cache_key] = result
            print(f"Cached result for query: {query_data.get('query', 'N/A')}")

        return result
```

## Database Integration

### Direct Database Access

```python
from sqlalchemy import create_engine, text
import pandas as pd

def get_database_connection():
    """Get direct database connection for advanced queries"""
    database_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    engine = create_engine(database_url)
    return engine

def advanced_analytics(run_id: str) -> pd.DataFrame:
    """Perform advanced analytics on workflow results"""
    engine = get_database_connection()

    query = text("""
    SELECT
        r.title,
        r.authors,
        r.year,
        r.source,
        s.include_exclude,
        s.reason,
        a.total_score,
        a.color_label
    FROM records r
    LEFT JOIN screening s ON r.id = s.record_id
    LEFT JOIN appraisal a ON r.id = a.record_id
    WHERE r.run_id = :run_id
    ORDER BY a.total_score DESC NULLS LAST
    """)

    return pd.read_sql(query, engine, params={"run_id": run_id})
```

## Testing Integration

### Integration Test Example

```python
import pytest
import httpx

@pytest.mark.asyncio
async def test_complete_workflow_integration():
    """Test complete workflow integration"""
    async with httpx.AsyncClient() as client:
        # Test data
        test_query = "effectiveness of problem-based learning in medical education"

        # Execute workflow
        response = await client.post(
            "http://localhost:8000/run",
            json={"query": test_query},
            timeout=300.0
        )

        assert response.status_code == 200
        result = response.json()

        # Validate response structure
        assert "run_id" in result
        assert "prisma" in result
        assert result["prisma"]["identified"] > 0

        # Test export functionality
        run_id = result["run_id"]
        export_response = await client.get(
            f"http://localhost:8000/runs/{run_id}/export/records.json"
        )

        assert export_response.status_code == 200
        export_data = export_response.json()
        assert len(export_data) > 0

@pytest.mark.asyncio
async def test_lico_workflow_integration():
    """Test LICO-based workflow integration"""
    async with httpx.AsyncClient() as client:
        lico_data = {
            "learner": "nursing students",
            "intervention": "clinical simulation",
            "context": "undergraduate education",
            "outcome": "clinical confidence"
        }

        # Test PRESS planning
        press_response = await client.post(
            "http://localhost:8000/press/plan",
            json=lico_data
        )

        assert press_response.status_code == 200
        press_plan = press_response.json()

        # Validate PRESS plan structure
        assert "question_lico" in press_plan
        assert "strategies" in press_plan
        assert "checklist" in press_plan
```

## Production Deployment

### Docker Configuration

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose Setup

```yaml
version: '3.8'

services:
  evidence-assistant:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@db:5432/evidence_db
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - SERPAPI_API_KEY=${SERPAPI_API_KEY}
    depends_on:
      - db
    volumes:
      - ./logs:/app/logs

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=evidence_db
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

### Health Monitoring

```python
async def health_check_integration():
    """Comprehensive health check for monitoring"""
    async with httpx.AsyncClient() as client:
        checks = {}

        # API health
        try:
            health_response = await client.get("http://localhost:8000/health")
            checks["api"] = health_response.status_code == 200
        except:
            checks["api"] = False

        # Database connectivity
        try:
            sources_response = await client.get("http://localhost:8000/sources/test")
            checks["database"] = sources_response.status_code == 200
        except:
            checks["database"] = False

        # AI services
        try:
            ai_response = await client.get("http://localhost:8000/ai/status")
            checks["ai"] = ai_response.json().get("available", False)
        except:
            checks["ai"] = False

        return {
            "status": "healthy" if all(checks.values()) else "degraded",
            "checks": checks,
            "timestamp": time.time()
        }
```

## Security Considerations

### API Key Management

```python
import os
from functools import lru_cache

@lru_cache()
def get_api_keys():
    """Securely retrieve API keys from environment"""
    return {
        "openai": os.getenv("OPENAI_API_KEY"),
        "serpapi": os.getenv("SERPAPI_API_KEY"),
        "semantic_scholar": os.getenv("S2_API_KEY"),
        "langsmith": os.getenv("LANGSMITH_API_KEY")
    }

def validate_api_keys():
    """Validate that required API keys are present"""
    keys = get_api_keys()

    if not keys["openai"]:
        raise ValueError("OPENAI_API_KEY is required for AI functionality")

    # Optional keys with warnings
    if not keys["serpapi"]:
        print("Warning: SERPAPI_API_KEY not set - Google Scholar search disabled")

    if not keys["semantic_scholar"]:
        print("Warning: S2_API_KEY not set - Semantic Scholar search may be limited")
```

### Rate Limiting

```python
import asyncio
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self, max_requests: int = 100, time_window: int = 3600):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = defaultdict(list)

    async def check_rate_limit(self, client_id: str) -> bool:
        """Check if client is within rate limits"""
        now = time.time()

        # Clean old requests
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if now - req_time < self.time_window
        ]

        # Check limit
        if len(self.requests[client_id]) >= self.max_requests:
            return False

        # Record new request
        self.requests[client_id].append(now)
        return True
```

This integration guide provides comprehensive coverage of all major integration patterns, error handling, performance optimization, and production deployment considerations for the Evidence Assistant API.