# tests/config/test_env.py
"""
Test environment configuration for E2E testing.
Sets up SQLite test database and test environment variables.
"""
import os
import tempfile
from pathlib import Path

# Test database configuration
TEST_DB_URL = "sqlite:///test_literature_review.db"
TEST_DB_FILE = "test_literature_review.db"

# Test environment variables
TEST_ENV = {
    "DATABASE_URL": TEST_DB_URL,
    "LOG_LEVEL": "DEBUG",
    "PRESS_YEAR_MIN": "2020-",
    # Mock API keys for testing (don't use real ones)
    "OPENAI_API_KEY": "test-openai-key",
    "LANGSMITH_API_KEY": "test-langsmith-key",
    "SERPAPI_API_KEY": "test-serpapi-key",
    "S2_API_KEY": "test-s2-key",
    # Enable mock mode to prevent real API calls
    "LLM_MOCK_MODE": "true",
    "API_MOCK_MODE": "true"
}

def setup_test_env():
    """Set up test environment variables."""
    for key, value in TEST_ENV.items():
        os.environ[key] = value

def cleanup_test_db():
    """Clean up test database file."""
    if os.path.exists(TEST_DB_FILE):
        os.remove(TEST_DB_FILE)

def get_test_db_path():
    """Get path to test database."""
    return Path.cwd() / TEST_DB_FILE