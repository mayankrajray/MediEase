"""Alembic environment: runs migrations against the database in settings.

The URL comes from ``load_settings()`` (fail fast with CFG_INVALID, like the
API), never from alembic.ini or a raw environment variable. Migrations run as
their own one-off process (the compose ``migrate`` service), never inside the
API at start-up (CLAUDE.md "Schema changes run as a discrete step").
"""

from __future__ import annotations

from alembic import context

from mediease_api.adapters.db.engine import build_engine
from mediease_api.adapters.db.models import Base
from mediease_api.config.logging import configure_logging
from mediease_api.config.settings import load_settings

settings = load_settings()
configure_logging(settings)

# The declarative metadata, so `alembic revision --autogenerate` can compare the
# models with the database (review its output; revisions are kept hand-written).
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (``alembic upgrade head --sql``)."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in one transaction on a live connection.

    PostgreSQL DDL is transactional, so a failed migration leaves the schema
    unchanged (RUNBOOK "Migration failed").
    """
    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
