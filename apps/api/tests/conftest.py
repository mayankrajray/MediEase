"""Shared pytest fixtures.

Settings are read from the process environment, so every test starts from a
clean, explicit set of variables. Values are synthetic (CLAUDE.md: no real data
outside production).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from mediease_api.bootstrap import create_app
from mediease_api.config.settings import AppSettings
from mediease_api.ports.readiness import ReadinessError

SetEnv = Callable[[dict[str, str]], None]

# Every variable AppSettings reads. Cleared before each test that uses set_env.
_MANAGED_VARS = ("APP_ENV", "LOG_LEVEL", "DB_ECHO_PARAMS", "DATABASE_URL", "COOKIE_SECURE")

_VALID_TEST_ENV = {
    "APP_ENV": "test",
    "LOG_LEVEL": "INFO",
    "DB_ECHO_PARAMS": "false",
    "DATABASE_URL": "postgresql+psycopg://mediease:test-password@localhost:5432/mediease_test",
    "COOKIE_SECURE": "false",
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
    return create_app(AppSettings(), database_check=database_check)  # type: ignore[call-arg]


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
