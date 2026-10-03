"""Migration tests against a throwaway PostgreSQL database (ADR-0004).

Each test creates its own database and drops it afterwards, so downgrades
never touch the developer's data. Proves the history has one head, upgrades
and downgrades cleanly, creates exactly the documented tables, matches the
SQLAlchemy models, and that env.py takes its URL from the settings.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from mediease_api.adapters.db.models import Base
from tests.conftest import ALEMBIC_INI, SetEnv, scratch_database

HEAD = "0005"
M1_TABLES = ["alembic_version", "clinic_memberships", "clinics", "doctors", "users"]
M1_P2_TABLES = sorted([*M1_TABLES, "refresh_tokens"])
M1_P4_TABLES = sorted([*M1_P2_TABLES, "audit_events"])
M1_P5_TABLES = sorted([*M1_P4_TABLES, "onboarding_checklists"])


@pytest.fixture
def scratch_database_url(database_url: str) -> Iterator[str]:
    with scratch_database(database_url, "mediease_migrations") as url:
        yield url


@pytest.fixture
def alembic_config(scratch_database_url: str, set_env: SetEnv, valid_env: dict[str, str]) -> Config:
    # env.py calls load_settings(), so the target database is chosen through
    # DATABASE_URL exactly as in the migrate container.
    set_env({**valid_env, "APP_ENV": "local", "DATABASE_URL": scratch_database_url})
    return Config(str(ALEMBIC_INI))


def _current_revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if not inspect(conn).has_table("alembic_version"):
                return None
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def _tables(url: str) -> list[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return sorted(inspect(conn).get_table_names())
    finally:
        engine.dispose()


def test_migration_history_has_a_single_head(alembic_config: Config) -> None:
    assert ScriptDirectory.from_config(alembic_config).get_heads() == [HEAD]


def test_migrations_upgrade_downgrade_upgrade_round_trip(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "head")
    assert _current_revision(scratch_database_url) == HEAD

    command.upgrade(alembic_config, "head")  # re-running is a no-op
    assert _current_revision(scratch_database_url) == HEAD

    command.downgrade(alembic_config, "base")
    assert _current_revision(scratch_database_url) is None
    assert _tables(scratch_database_url) == ["alembic_version"]

    command.upgrade(alembic_config, "head")
    assert _current_revision(scratch_database_url) == HEAD


def test_baseline_creates_no_application_tables(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0001")
    assert _tables(scratch_database_url) == ["alembic_version"]


def test_0002_creates_the_m1_tables(alembic_config: Config, scratch_database_url: str) -> None:
    command.upgrade(alembic_config, "0002")
    assert _tables(scratch_database_url) == M1_TABLES

    command.downgrade(alembic_config, "0001")
    assert _tables(scratch_database_url) == ["alembic_version"]


def _user_columns(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return {column["name"] for column in inspect(conn).get_columns("users")}
    finally:
        engine.dispose()


def test_0003_adds_credentials_and_refresh_tokens(
    alembic_config: Config, scratch_database_url: str
) -> None:
    credentials = {"password_hash", "failed_login_count", "locked_until", "last_login_at"}
    command.upgrade(alembic_config, "0003")
    assert _tables(scratch_database_url) == M1_P2_TABLES
    assert credentials <= _user_columns(scratch_database_url)

    command.downgrade(alembic_config, "0002")
    assert _tables(scratch_database_url) == M1_TABLES
    assert not credentials & _user_columns(scratch_database_url)


def _views(url: str) -> list[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return sorted(inspect(conn).get_view_names())
    finally:
        engine.dispose()


def test_0004_adds_audit_events_and_the_activity_view(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0004")
    assert _tables(scratch_database_url) == M1_P4_TABLES
    assert _views(scratch_database_url) == ["v_clinic_activity"]

    command.downgrade(alembic_config, "0003")
    assert _tables(scratch_database_url) == M1_P2_TABLES
    assert _views(scratch_database_url) == []


def _membership_columns(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return {c["name"] for c in inspect(conn).get_columns("clinic_memberships")}
    finally:
        engine.dispose()


def test_0005_adds_staff_invites_and_the_onboarding_checklist(
    alembic_config: Config, scratch_database_url: str
) -> None:
    invite = {"invite_token_hash", "invite_expires_at", "invite_accepted_at"}
    command.upgrade(alembic_config, "0005")
    assert _tables(scratch_database_url) == M1_P5_TABLES
    assert invite <= _membership_columns(scratch_database_url)

    command.downgrade(alembic_config, "0004")
    assert _tables(scratch_database_url) == M1_P4_TABLES
    assert not invite & _membership_columns(scratch_database_url)


def test_models_match_migrations(alembic_config: Config, scratch_database_url: str) -> None:
    """Autogenerate finds nothing to change: models and hand-written migrations agree."""
    assert sorted(Base.metadata.tables) == [t for t in M1_P5_TABLES if t != "alembic_version"]
    command.upgrade(alembic_config, "head")
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()
