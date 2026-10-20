"""Migration tests against a throwaway PostgreSQL database (ADR-0004).

Each test creates its own database and drops it afterwards, so downgrades
never touch the developer's data. Proves the history has one head, upgrades
and downgrades cleanly, creates exactly the documented tables, matches the
SQLAlchemy models, and that env.py takes its URL from the settings.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from mediease_api.adapters.db.models import Base
from tests.conftest import ALEMBIC_INI, SetEnv, scratch_database

HEAD = "0018"
M1_TABLES = ["alembic_version", "clinic_memberships", "clinics", "doctors", "users"]
M1_P2_TABLES = sorted([*M1_TABLES, "refresh_tokens"])
M1_P4_TABLES = sorted([*M1_P2_TABLES, "audit_events"])
M1_P5_TABLES = sorted([*M1_P4_TABLES, "onboarding_checklists"])
M2_P1_TABLES = sorted([*M1_P5_TABLES, "patients"])
M3_P1_TABLES = sorted([*M2_P1_TABLES, "doctor_schedules", "schedule_exceptions", "sessions"])
M3_P2_TABLES = sorted([*M3_P1_TABLES, "appointment_status_history", "appointments"])
M4_P1_TABLES = sorted([*M3_P2_TABLES, "visit_addenda", "visits"])
M4_P2_TABLES = sorted([*M4_P1_TABLES, "prescription_items", "prescriptions"])
M4_P3_TABLES = sorted([*M4_P2_TABLES, "rx_favourites", "rx_templates"])
M4_P5_TABLES = sorted([*M4_P3_TABLES, "patient_links", "public_rate_limits"])
M5_P1_TABLES = sorted([*M4_P5_TABLES, "jobs"])
M5_P2_TABLES = sorted([*M5_P1_TABLES, "messages"])
M5_P3_TABLES = sorted([*M5_P2_TABLES, "webhook_events"])
M5_P4_TABLES = sorted([*M5_P3_TABLES, "reminders"])


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


def _clinic_columns(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return {c["name"] for c in inspect(conn).get_columns("clinics")}
    finally:
        engine.dispose()


def test_0006_adds_patients_and_gives_existing_clinics_a_code_prefix(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0005")
    names = {
        "Sample Clinic": "SC",
        "Apollo": "AP",
        "Dr. Rao's Children & Family Clinic": "DRSC",
        "123": "CL",
    }
    engine = create_engine(scratch_database_url)
    try:
        with engine.begin() as conn:
            for n, name in enumerate(names):
                conn.execute(
                    text(
                        "INSERT INTO clinics (id, name, slug, timezone, status, specialties, "
                        "created_at, updated_at) VALUES (gen_random_uuid(), :name, :slug, "
                        "'Asia/Kolkata', 'ACTIVE', '{}', now(), now())"
                    ),
                    {"name": name, "slug": f"migrated-clinic-{n}"},
                )

        command.upgrade(alembic_config, "0006")

        assert _tables(scratch_database_url) == M2_P1_TABLES
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT name, patient_code_prefix, next_patient_seq FROM clinics")
            ).all()
        assert {name: (prefix, seq) for name, prefix, seq in rows} == {
            name: (prefix, 1) for name, prefix in names.items()
        }

        command.downgrade(alembic_config, "0005")
        assert _tables(scratch_database_url) == M1_P5_TABLES
        assert not {"patient_code_prefix", "next_patient_seq"} & _clinic_columns(
            scratch_database_url
        )
    finally:
        engine.dispose()


def test_0007_adds_schedules_and_sessions_and_tokens_mode_for_existing_clinics(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0006")
    engine = create_engine(scratch_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinics (id, name, slug, timezone, status, specialties, "
                    "patient_code_prefix, created_at, updated_at) VALUES (gen_random_uuid(), "
                    "'Sample Clinic', 'migrated-clinic', 'Asia/Kolkata', 'ACTIVE', '{}', 'SC', "
                    "now(), now())"
                )
            )

        command.upgrade(alembic_config, "0007")

        assert _tables(scratch_database_url) == M3_P1_TABLES
        with engine.connect() as conn:
            modes = conn.execute(text("SELECT booking_mode FROM clinics")).scalars().all()
        assert modes == ["TOKENS"]

        command.downgrade(alembic_config, "0006")
        assert _tables(scratch_database_url) == M2_P1_TABLES
        assert "booking_mode" not in _clinic_columns(scratch_database_url)
    finally:
        engine.dispose()


def test_0008_adds_appointments_whose_indexes_back_the_booking_rules(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0008")
    assert _tables(scratch_database_url) == M3_P2_TABLES
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            indexes = {i["name"]: i for i in inspect(conn).get_indexes("appointments")}
        assert indexes["uq_appointments_session_id_slot_start_active"]["unique"]
        assert indexes["uq_appointments_session_id_patient_id_active"]["unique"]

        command.downgrade(alembic_config, "0007")
        assert _tables(scratch_database_url) == M3_P1_TABLES
    finally:
        engine.dispose()


def test_0009_adds_visits_and_append_only_addenda(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0009")
    assert _tables(scratch_database_url) == M4_P1_TABLES
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            triggers = conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE tgrelid = 'visit_addenda'::regclass"
                    " AND NOT tgisinternal ORDER BY tgname"
                )
            ).scalars()
            assert list(triggers) == [
                "trg_visit_addenda_no_truncate",
                "trg_visit_addenda_no_update_delete",
            ]
            unique = {c["name"] for c in inspect(conn).get_unique_constraints("visits")}
            assert "uq_visits_appointment_id" in unique

        command.downgrade(alembic_config, "0008")
        assert _tables(scratch_database_url) == M3_P2_TABLES
        with engine.connect() as conn:
            gone = conn.execute(
                text("SELECT count(*) FROM pg_proc WHERE proname = 'visit_addenda_append_only'")
            ).scalar()
            assert gone == 0
    finally:
        engine.dispose()


def test_0010_adds_prescriptions_guarded_by_triggers(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0010")
    assert _tables(scratch_database_url) == M4_P2_TABLES
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            triggers = conn.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN"
                    " ('prescriptions'::regclass, 'prescription_items'::regclass) ORDER BY tgname"
                )
            ).scalars()
            assert list(triggers) == [
                "trg_prescription_items_frozen",
                "trg_prescription_items_no_truncate",
                "trg_prescriptions_immutable",
                "trg_prescriptions_no_truncate",
            ]
            indexes = {i["name"]: i for i in inspect(conn).get_indexes("prescriptions")}
            assert indexes["uq_prescriptions_visit_id_draft"]["unique"]

        command.downgrade(alembic_config, "0009")
        assert _tables(scratch_database_url) == M4_P1_TABLES
        with engine.connect() as conn:
            left = conn.execute(
                text(
                    "SELECT count(*) FROM pg_proc WHERE proname IN"
                    " ('prescriptions_immutable', 'prescription_items_frozen')"
                )
            ).scalar()
            assert left == 0
    finally:
        engine.dispose()


def test_0011_adds_the_doctors_library_and_the_name_index(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0011")
    assert _tables(scratch_database_url) == M4_P3_TABLES
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            items = {i["name"] for i in inspect(conn).get_indexes("prescription_items")}
            assert "ix_prescription_items_clinic_id_medicine_name" in items
            favs = {i["name"]: i for i in inspect(conn).get_indexes("rx_favourites")}
            assert favs["uq_rx_favourites_doctor_id_name"]["unique"]
        command.downgrade(alembic_config, "0010")
        assert _tables(scratch_database_url) == M4_P2_TABLES
    finally:
        engine.dispose()


def test_0012_gives_every_clinic_a5_prescriptions_and_allows_only_a5_or_a4(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0011")
    engine = create_engine(scratch_database_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinics (id, name, slug, timezone, status, specialties, "
                    "patient_code_prefix, created_at, updated_at) VALUES (gen_random_uuid(), "
                    "'Sample Clinic', 'migrated-clinic', 'Asia/Kolkata', 'ACTIVE', '{}', 'SC', "
                    "now(), now())"
                )
            )

        command.upgrade(alembic_config, "0012")

        with engine.connect() as conn:
            sizes = conn.execute(text("SELECT rx_paper_size FROM clinics")).scalars().all()
            assert sizes == ["A5"]
            checks = {c["name"] for c in inspect(conn).get_check_constraints("clinics")}
            assert "ck_clinics_rx_paper_size" in checks

        command.downgrade(alembic_config, "0011")
        assert "rx_paper_size" not in _clinic_columns(scratch_database_url)
        assert _tables(scratch_database_url) == M4_P3_TABLES
    finally:
        engine.dispose()


def test_0013_adds_patient_links_rate_limits_and_the_layout_version(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0013")
    assert _tables(scratch_database_url) == M4_P5_TABLES
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            indexes = {i["name"]: i for i in inspect(conn).get_indexes("patient_links")}
            assert indexes["uq_patient_links_prescription_id_active"]["unique"]
            columns = {c["name"] for c in inspect(conn).get_columns("prescriptions")}
            assert "layout_version" in columns
        command.downgrade(alembic_config, "0012")
        assert _tables(scratch_database_url) == M4_P3_TABLES
        with engine.connect() as conn:
            columns = {c["name"] for c in inspect(conn).get_columns("prescriptions")}
            assert "layout_version" not in columns
    finally:
        engine.dispose()


def test_0014_adds_jobs_with_partial_indexes_and_the_health_view(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0014")
    assert _tables(scratch_database_url) == M5_P1_TABLES
    assert "v_job_health" in _views(scratch_database_url)
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            indexes = {i["name"]: i for i in inspect(conn).get_indexes("jobs")}
            assert indexes["uq_jobs_dedupe_key"]["unique"]
            assert {"ix_jobs_claim", "ix_jobs_running", "ix_jobs_clinic_id"} <= set(indexes)
            definition = conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_jobs_dedupe_key'")
            ).scalar_one()
            # R9c: only live jobs hold their key; a cancelled or dead one does not.
            assert "queued" in definition and "succeeded" in definition
            assert "cancelled" not in definition and "dead" not in definition
            checks = {c["name"] for c in inspect(conn).get_check_constraints("jobs")}
            assert {
                "ck_jobs_state",
                "ck_jobs_kind_format",
                "ck_jobs_attempts_range",
                "ck_jobs_lock_when_running",
                "ck_jobs_system_kind",
            } <= checks
        command.downgrade(alembic_config, "0013")
        assert _tables(scratch_database_url) == M4_P5_TABLES
        assert "v_job_health" not in _views(scratch_database_url)
    finally:
        engine.dispose()


def test_0015_adds_messages_with_unique_keys_and_the_health_view(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0015")
    assert _tables(scratch_database_url) == M5_P2_TABLES
    assert {"v_job_health", "v_message_health"} <= set(_views(scratch_database_url))
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            uniques = {u["name"] for u in inspect(conn).get_unique_constraints("messages")}
            # R6, AC4: one row per idempotency key; P3's webhooks find a row by provider ID.
            assert {"uq_messages_idempotency_key", "uq_messages_provider_message_id"} <= uniques
            indexes = {i["name"] for i in inspect(conn).get_indexes("messages")}
            assert {
                "ix_messages_clinic_id_patient_id",
                "ix_messages_clinic_id_source_type_source_id",
            } <= indexes
            checks = {c["name"] for c in inspect(conn).get_check_constraints("messages")}
            assert {
                "ck_messages_channel",
                "ck_messages_status",
                "ck_messages_sent_has_provider_id",
                "ck_messages_failed_has_code",
                "ck_messages_started_only_queued",
            } <= checks
            columns = {c["name"] for c in inspect(conn).get_columns("messages")}
            # Decision 1A: the number is only ever stored encrypted.
            assert "to_phone_encrypted" in columns and "to_phone_e164" not in columns
        command.downgrade(alembic_config, "0014")
        assert _tables(scratch_database_url) == M5_P1_TABLES
        assert "v_message_health" not in _views(scratch_database_url)
    finally:
        engine.dispose()


def test_0016_adds_webhook_events_and_the_webhook_system_kinds(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0016")
    assert _tables(scratch_database_url) == M5_P3_TABLES
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            uniques = {u["name"] for u in inspect(conn).get_unique_constraints("webhook_events")}
            assert "uq_webhook_events_event_key" in uniques  # one row per body (R13)
            check = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname = 'ck_jobs_system_kind'"
                )
            ).scalar_one()
            assert "process_webhook_event" in check and "reconcile_messages" in check
            columns = {c["name"] for c in inspect(conn).get_columns("v_message_health")}
            assert "unconfirmed_24h" in columns
        command.downgrade(alembic_config, "0015")
        assert _tables(scratch_database_url) == M5_P2_TABLES
        with engine.connect() as conn:
            columns = {c["name"] for c in inspect(conn).get_columns("v_message_health")}
            assert "unconfirmed_24h" not in columns
            check = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname = 'ck_jobs_system_kind'"
                )
            ).scalar_one()
            assert "reconcile_messages" not in check
    finally:
        engine.dispose()


def test_0017_adds_reminders_with_one_scheduled_per_chain(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0017")
    assert _tables(scratch_database_url) == M5_P4_TABLES
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            definition = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes"
                    " WHERE indexname = 'uq_reminders_source_id_scheduled'"
                )
            ).scalar_one()
            assert "UNIQUE" in definition and "SCHEDULED" in definition
            kinds = conn.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                    " WHERE conname = 'ck_jobs_system_kind'"
                )
            ).scalar_one()
            assert "schedule_no_shows" in kinds
        command.downgrade(alembic_config, "0016")
        assert _tables(scratch_database_url) == M5_P3_TABLES
    finally:
        engine.dispose()


def _check(conn: Any, name: str) -> str:
    return str(
        conn.execute(
            text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n"),
            {"n": name},
        ).scalar_one()
    )


def test_0018_indexes_patients_by_number_and_allows_opt_out_replies(
    alembic_config: Config, scratch_database_url: str
) -> None:
    command.upgrade(alembic_config, "0018")
    assert _tables(scratch_database_url) == M5_P4_TABLES  # no new table
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            indexes = {i["name"]: i for i in inspect(conn).get_indexes("patients")}
            assert indexes["ix_patients_phone_e164"]["column_names"] == ["phone_e164"]
            assert "OPT_OUT" in _check(conn, "ck_messages_source_type")
        command.downgrade(alembic_config, "0017")
        with engine.connect() as conn:
            names = {i["name"] for i in inspect(conn).get_indexes("patients")}
            assert "ix_patients_phone_e164" not in names
            assert "OPT_OUT" not in _check(conn, "ck_messages_source_type")
    finally:
        engine.dispose()


def test_models_match_migrations(alembic_config: Config, scratch_database_url: str) -> None:
    """Autogenerate finds nothing to change: models and hand-written migrations agree."""
    assert sorted(Base.metadata.tables) == [t for t in M5_P4_TABLES if t != "alembic_version"]
    command.upgrade(alembic_config, "head")
    engine = create_engine(scratch_database_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()
