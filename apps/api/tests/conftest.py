"""Shared pytest fixtures.

Settings read from the process environment, so each test starts from a clean,
controlled set of variables to keep cases independent and deterministic.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

# The environment variables AppSettings understands in M0-P2/M0-P3.
_MANAGED_VARS = (
    "APP_ENV",
    "LOG_LEVEL",
    "DB_ECHO_PARAMS",
    "DATABASE_URL",
    "COOKIE_SECURE",
    "API_PORT",
)

# A minimal, valid local configuration used as the baseline for most tests.
VALID_LOCAL_ENV = {
    "APP_ENV": "local",
    "LOG_LEVEL": "INFO",
    "DB_ECHO_PARAMS": "false",
    "DATABASE_URL": "postgresql+psycopg://mediease:pw@localhost:5432/mediease",
    "COOKIE_SECURE": "false",
}


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove all managed vars so a test sets exactly what it needs."""
    for var in _MANAGED_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def set_env(monkeypatch: pytest.MonkeyPatch, clean_env: None) -> Iterator[object]:
    """Return a helper that applies a dict of env vars for the test."""

    def _apply(env: dict[str, str]) -> None:
        for key, value in env.items():
            monkeypatch.setenv(key, value)

    yield _apply
