import os

DB_PATH = 'test_persist.db'

# Ensure a clean database before importing the application modules
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

os.environ['DATABASE_URL'] = f'sqlite:///{DB_PATH}'

from app.persist import persist_run
from app.db import get_session, SearchRun


def test_persist_run_creates_single_run():
    state = {"records": [], "screenings": [], "appraisals": []}
    run_id = persist_run(state)
    assert run_id
    with get_session() as s:
        runs = s.query(SearchRun).all()
        assert len(runs) == 1
        assert runs[0].id == run_id

    # Clean up test database file (try to remove, ignore errors on Windows)
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except (PermissionError, OSError):
        pass  # File may be locked on Windows