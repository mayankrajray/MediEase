"""Shared pytest fixtures.

Settings are read from the process environment, so every test starts from a
clean, explicit set of variables. Values are synthetic (CLAUDE.md: no real data
outside production).
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from flask import Flask
from flask.testing import FlaskClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.db.models import Base
from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork, build_session_factory
from mediease_api.adapters.security.argon2_hasher import Argon2PasswordHasher
from mediease_api.bootstrap import create_app
from mediease_api.config.logging import configure_logging
from mediease_api.config.settings import AppEnv, AppSettings
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.user import User
from mediease_api.ports.readiness import ReadinessError
from tests.builders import LATER, NOW, a_clinic, a_doctor, a_membership, a_user

SetEnv = Callable[[dict[str, str]], None]

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

# Every variable AppSettings reads. Cleared before each test that uses set_env.
_MANAGED_VARS = (
    "APP_ENV",
    "LOG_LEVEL",
    "DB_ECHO_PARAMS",
    "DATABASE_URL",
    "COOKIE_SECURE",
    "PUBLIC_BASE_URL",
    "JWT_SIGNING_KEY",
    "AUDIT_IP_SALT",
    "ACCESS_TOKEN_TTL_SECONDS",
    "REFRESH_TOKEN_TTL_SECONDS",
    "BLOB_STORAGE",
    "BLOB_LOCAL_DIR",
    "S3_BUCKET",
    "S3_REGION",
    "S3_ENDPOINT_URL",
)

# Synthetic, test-only secrets (>= 32 characters each).
TEST_SIGNING_KEY = "test-only-signing-key-0123456789abcdef"
TEST_IP_SALT = "test-only-audit-ip-salt-0123456789abcdef"

_VALID_TEST_ENV = {
    "APP_ENV": "test",
    "LOG_LEVEL": "INFO",
    "DB_ECHO_PARAMS": "false",
    "DATABASE_URL": "postgresql+psycopg://mediease:test-password@localhost:5432/mediease_test",
    "COOKIE_SECURE": "false",
    # https, so the deployed-environment rules can be tested by changing APP_ENV alone.
    "PUBLIC_BASE_URL": "https://test.mediease.example",
    "JWT_SIGNING_KEY": TEST_SIGNING_KEY,
    "AUDIT_IP_SALT": TEST_IP_SALT,
}


class FakeDatabaseCheck:
    """In-memory DatabaseCheck: passes, or raises the error a test assigns."""

    def __init__(self) -> None:
        self.error: ReadinessError | None = None
        self.calls = 0

    def check(self) -> None:
        self.calls += 1
        if self.error is not None:
            raise self.error


def _json_log_settings() -> AppSettings:
    return AppSettings(
        APP_ENV=AppEnv.TEST,
        DATABASE_URL=_VALID_TEST_ENV["DATABASE_URL"],
        JWT_SIGNING_KEY=SecretStr(TEST_SIGNING_KEY),
        AUDIT_IP_SALT=SecretStr(TEST_IP_SALT),
    )


LogReader = Callable[[], list[dict[str, Any]]]


@pytest.fixture
def json_logs(capsys: pytest.CaptureFixture[str]) -> LogReader:
    """JSON log events written to stdout from now on in this test.

    Use this instead of ``structlog.testing.capture_logs``: once any app has
    configured logging, structlog caches loggers on first use and
    ``capture_logs`` no longer sees their events.
    """
    configure_logging(_json_log_settings())
    capsys.readouterr()

    def _read() -> list[dict[str, Any]]:
        lines = capsys.readouterr().out.splitlines()
        return [json.loads(line) for line in lines if line.startswith("{")]

    return _read


@pytest.fixture
def valid_env() -> dict[str, str]:
    """A valid APP_ENV=test configuration; tests copy and override it."""
    return dict(_VALID_TEST_ENV)


@pytest.fixture
def set_env(monkeypatch: pytest.MonkeyPatch) -> SetEnv:
    """Clear the managed variables and return a helper that sets new ones."""
    for var in _MANAGED_VARS:
        monkeypatch.delenv(var, raising=False)

    def _apply(env: dict[str, str]) -> None:
        for key, value in env.items():
            monkeypatch.setenv(key, value)

    return _apply


@pytest.fixture
def database_check() -> FakeDatabaseCheck:
    return FakeDatabaseCheck()


@pytest.fixture
def app(set_env: SetEnv, valid_env: dict[str, str], database_check: FakeDatabaseCheck) -> Flask:
    """An app from the composition root with a fake database check (no network)."""
    set_env(valid_env)
    return create_app(
        AppSettings(),  # type: ignore[call-arg]
        database_check=database_check,
        password_hasher=CHEAP_HASHER,
    )


@pytest.fixture
def client(app: Flask) -> Iterator[FlaskClient]:
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL of a real PostgreSQL for integration tests (TESTING.md: no mocks for the db).

    `make test-api` derives it from .env and points at the compose `db` on
    localhost; CI sets it to its PostgreSQL service. Missing is a failure, not
    a skip, so database behaviour is never silently untested.
    """
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL is not set. Run tests with `make test-api` "
            "(start the database first with `make up`), or export it yourself."
        )
    return url


@contextmanager
def scratch_database(database_url: str, prefix: str) -> Iterator[str]:
    """Create an empty, uniquely named database; drop it on exit.

    Tests that migrate or write data never touch the developer's database.
    """
    name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin = create_engine(database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(database_url).set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def upgrade_to_head(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `alembic upgrade head` on ``url`` exactly as the migrate container does."""
    # env.py calls load_settings(), so the target is chosen through DATABASE_URL.
    for var in _MANAGED_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("JWT_SIGNING_KEY", TEST_SIGNING_KEY)
    monkeypatch.setenv("AUDIT_IP_SALT", TEST_IP_SALT)
    command.upgrade(Config(str(ALEMBIC_INI)), "head")


@pytest.fixture(scope="session")
def migrated_database_url(database_url: str) -> Iterator[str]:
    """One database per test session with every migration applied."""
    with scratch_database(database_url, "mediease_it") as url:
        with pytest.MonkeyPatch.context() as monkeypatch:
            upgrade_to_head(url, monkeypatch)
        yield url


@pytest.fixture(scope="session")
def session_factory(migrated_database_url: str) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(migrated_database_url, hide_parameters=True)
    yield build_session_factory(engine)
    engine.dispose()


UowFactory = Callable[[], SqlAlchemyUnitOfWork]

# Tables whose triggers refuse TRUNCATE; the test reset lifts them deliberately.
GUARDED_TABLES = ("audit_events", "visit_addenda", "prescriptions", "prescription_items")


@pytest.fixture
def uow_factory(session_factory: sessionmaker[Session]) -> Iterator[UowFactory]:
    """New units of work on the migrated database; every table is emptied afterwards."""
    yield lambda: SqlAlchemyUnitOfWork(session_factory)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with session_factory() as session:
        # audit_events refuses TRUNCATE in the database (FR-AUD-02). Tests must
        # still be able to reset, so this is the one place that lifts the guard
        # — the same deliberate, visible step operations would have to take
        # (docs/RUNBOOK.md). Production never truncates it.
        # visit_addenda is append-only the same way (FR-VIS-05, migration 0009).
        # prescriptions and their items refuse TRUNCATE too (FR-RX-09, migration 0010).
        for guarded in GUARDED_TABLES:
            session.execute(text(f"ALTER TABLE {guarded} DISABLE TRIGGER USER"))
        session.execute(text(f"TRUNCATE {tables}"))
        for guarded in GUARDED_TABLES:
            session.execute(text(f"ALTER TABLE {guarded} ENABLE TRIGGER USER"))
        session.commit()


# --- HTTP against the real database (M1-P2) ------------------------------------------------

# Argon2id with minimal cost: same algorithm and code path, ~1 ms instead of ~50 ms.
CHEAP_HASHER = Argon2PasswordHasher(time_cost=1, memory_cost_kib=8, parallelism=1)
DEMO_PASSWORD = "synthetic-Passw0rd-for-tests"  # gitleaks:allow (synthetic test value)


def make_db_app(database_url: str, *, cookie_secure: bool = False) -> Flask:
    # APP_ENV=local: the compose db's password is a change-me placeholder.
    settings = AppSettings(
        APP_ENV=AppEnv.LOCAL,
        DATABASE_URL=database_url,
        COOKIE_SECURE=cookie_secure,
        JWT_SIGNING_KEY=SecretStr(TEST_SIGNING_KEY),
        AUDIT_IP_SALT=SecretStr(TEST_IP_SALT),
    )
    return create_app(settings, password_hasher=CHEAP_HASHER)


@pytest.fixture
def db_client(migrated_database_url: str, uow_factory: UowFactory) -> Iterator[FlaskClient]:
    """A client for an app wired to the migrated test database (tables emptied after)."""
    with make_db_app(migrated_database_url).test_client() as test_client:
        yield test_client


def seed_staff(
    uow_factory: UowFactory,
    *,
    role: Role = Role.OWNER,
    password: str | None = DEMO_PASSWORD,
    **user_fields: object,
) -> User:
    """A user with an active membership in a new clinic (and a password unless None)."""
    user = a_user(password_hash=CHEAP_HASHER.hash(password) if password else None, **user_fields)
    clinic = a_clinic()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(user)
        uow.tenant(clinic.id).memberships.add(a_membership(clinic.id, user.id, role))
        uow.commit()
    return user


# --- Two clinics with all three roles (M1-P3 authorisation and tenancy tests) ---------------


@dataclass(frozen=True)
class Tenant:
    """One ACTIVE clinic with an owner, a doctor and a front desk, plus a doctor profile."""

    clinic: Clinic
    owner: User
    doctor_user: User
    desk: User
    doctor: Doctor

    def user_for(self, role: Role) -> User:
        return {Role.OWNER: self.owner, Role.DOCTOR: self.doctor_user, Role.FRONT_DESK: self.desk}[
            role
        ]


@dataclass(frozen=True)
class World:
    """Clinics A and B, a user who works in both, an ops user and a suspended clinic.

    One app for all of them; every ``client_for`` call gets its own cookie jar,
    so several users can act in the same test without sharing a session.
    """

    app: Flask
    a: Tenant
    b: Tenant
    multi: User  # FRONT_DESK in clinic A, OWNER in clinic B
    ops: User
    suspended_clinic: Clinic
    suspended_owner: User

    def anonymous(self) -> FlaskClient:
        return self.app.test_client()

    def client_for(self, user: User) -> FlaskClient:
        """A client that has signed ``user`` in (cookies set as a browser would hold them)."""
        client = self.app.test_client()
        assert user.email is not None
        resp = client.post(
            "/api/v1/auth/sign-in",
            json={"identifier": user.email.value, "password": DEMO_PASSWORD},
        )
        assert resp.status_code == 200, resp.get_json()
        return client


def _seed_tenant(uow: SqlAlchemyUnitOfWork, label: str) -> Tenant:
    clinic = a_clinic(name=f"{label} Sample Clinic")
    uow.clinics.add(clinic)
    staff = uow.tenant(clinic.id)
    users = {
        role: a_user(
            full_name=f"{label} {role.value.title()}",
            password_hash=CHEAP_HASHER.hash(DEMO_PASSWORD),
        )
        for role in (Role.OWNER, Role.DOCTOR, Role.FRONT_DESK)
    }
    for role, user in users.items():
        uow.users.add(user)
        staff.memberships.add(a_membership(clinic.id, user.id, role))
    doctor = a_doctor(clinic.id, user_id=users[Role.DOCTOR].id, display_name=f"Dr. {label} Sample")
    staff.doctors.add(doctor)
    clinic.activate(active_owner_count=1, now=NOW)
    uow.clinics.update(clinic)
    return Tenant(
        clinic=clinic,
        owner=users[Role.OWNER],
        doctor_user=users[Role.DOCTOR],
        desk=users[Role.FRONT_DESK],
        doctor=doctor,
    )


@pytest.fixture
def world(migrated_database_url: str, uow_factory: UowFactory) -> World:
    with uow_factory() as uow:
        a = _seed_tenant(uow, "Alpha")
        b = _seed_tenant(uow, "Beta")

        multi = a_user(full_name="Multi Clinic", password_hash=CHEAP_HASHER.hash(DEMO_PASSWORD))
        uow.users.add(multi)
        uow.tenant(a.clinic.id).memberships.add(
            a_membership(a.clinic.id, multi.id, Role.FRONT_DESK)
        )
        uow.tenant(b.clinic.id).memberships.add(a_membership(b.clinic.id, multi.id, Role.OWNER))

        ops = a_user(
            full_name="Platform Ops",
            is_platform_ops=True,
            password_hash=CHEAP_HASHER.hash(DEMO_PASSWORD),
        )
        uow.users.add(ops)

        suspended = a_clinic(name="Suspended Sample Clinic")
        suspended_owner = a_user(
            full_name="Suspended Owner", password_hash=CHEAP_HASHER.hash(DEMO_PASSWORD)
        )
        uow.clinics.add(suspended)
        uow.users.add(suspended_owner)
        uow.tenant(suspended.id).memberships.add(
            a_membership(suspended.id, suspended_owner.id, Role.OWNER)
        )
        suspended.activate(active_owner_count=1, now=NOW)
        suspended.suspend(now=LATER)
        uow.clinics.update(suspended)
        uow.commit()

    return World(
        app=make_db_app(migrated_database_url),
        a=a,
        b=b,
        multi=multi,
        ops=ops,
        suspended_clinic=suspended,
        suspended_owner=suspended_owner,
    )
