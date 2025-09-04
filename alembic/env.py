from __future__ import annotations
import os
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context

# --- Load your SQLAlchemy Base & models so autogenerate can see them ---
from app import db as app_db
target_metadata = app_db.Base.metadata  # Base is defined in app/db.py

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    """
    Pull DATABASE_URL from the environment; fall back to the same SQLite
    path your app/db.py uses so environments stay consistent.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        url = "sqlite:///artifacts.db"
    # Optional convenience: tolerate "+psycopg2" in URL for Postgres
    return url.replace("+psycopg2", "")


def include_object(object, name, type_, reflected, compare_to):
    """
    Exclude LangGraph checkpoint tables/indexes from autogenerate diffs.
    This prevents Alembic from proposing to drop them just because they’re
    not part of your ORM metadata.
    """
    if type_ in {"table", "index"} and (
        name == "checkpoints" or name.startswith("checkpoint_")
    ):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,   # <-- important
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool, future=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,  # <-- important
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
