"""Shared pytest fixtures.

Settings are read from the process environment, so every test starts from a
clean, explicit set of variables. Values are synthetic (CLAUDE.md: no real data
outside production).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from mediease_api.bootstrap import create_app
from mediease_api.config.settings import AppSettings

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
def app(set_env: SetEnv, valid_env: dict[str, str]) -> Flask:
    """An app built by the composition root from a valid test configuration."""
    set_env(valid_env)
    return create_app(AppSettings())  # type: ignore[call-arg]  # values come from the environment


@pytest.fixture
def client(app: Flask) -> Iterator[FlaskClient]:
    with app.test_client() as test_client:
        yield test_client
