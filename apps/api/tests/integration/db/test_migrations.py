"""Migration tests against a throwaway PostgreSQL database (ADR-0004).

Each test run creates its own database and drops it afterwards, so downgrades
never touch the developer's data. Proves the history has one head, upgrades
and downgrades cleanly, and that env.py takes its URL from the settings.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from tests.conftest import SetEnv

_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


@pytest.fixture
def scratch_database_url(database_url: str) -> Iterator[str]:
    """Create an empty database for one test and drop it afterwards."""
    name = f"mediease_migrations_{uuid.uuid4().hex[:12]}"
    admin = create_engine(database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(database_url).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def alembic_config(scratch_database_url: str, set_env: SetEnv, valid_env: dict[str, str]) -> Config:
    # env.py calls load_settings(), so the target database is chosen through
    # DATABASE_URL exactly as in the migrate container.
    set_env({**valid_env, "APP_ENV": "local", "DATABASE_URL": scratch_database_url})
    return Config(str(_ALEMBIC_INI))


def _current_revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if not inspect(conn).has_table("alembic_version"):
                return None
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def test_migration_history_has_a_single_head(alembic_config: Config) -> None:
    assert ScriptDirectory.from_config(alembic_config).get_heads() == ["0001"]


def test_migrations_upgrade_downgrade_upgrade_round_trip(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "head")
    assert _current_revision(scratch_database_url) == "0001"

    command.upgrade(alembic_config, "head")  # re-running is a no-op
    assert _current_revision(scratch_database_url) == "0001"

    command.downgrade(alembic_config, "base")
    assert _current_revision(scratch_database_url) is None

    command.upgrade(alembic_config, "head")
    assert _current_revision(scratch_database_url) == "0001"


def test_baseline_creates_no_application_tables(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "head")
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            assert inspect(conn).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()
