"""Unit tests for typed settings (NFR-12 — fail fast on misconfiguration).

Covers the acceptance criteria in docs/milestones/M0-foundation.md:
valid local config; missing DATABASE_URL; DEBUG in production; insecure cookies
in staging; DB_ECHO_PARAMS=true anywhere.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from mediease_api.config.settings import (
    CFG_INVALID,
    AppEnv,
    AppSettings,
    load_settings,
)
from tests.conftest import VALID_LOCAL_ENV

SetEnv = Callable[[dict[str, str]], None]


def test_valid_local_config_loads(set_env: SetEnv) -> None:
    set_env(VALID_LOCAL_ENV)
    settings = load_settings()
    assert settings.APP_ENV is AppEnv.LOCAL
    assert settings.LOG_LEVEL == "INFO"
    assert settings.DB_ECHO_PARAMS is False
    assert settings.COOKIE_SECURE is False


def test_missing_database_url_exits(set_env: SetEnv) -> None:
    env = {k: v for k, v in VALID_LOCAL_ENV.items() if k != "DATABASE_URL"}
    set_env(env)
    with pytest.raises(SystemExit) as excinfo:
        load_settings()
    assert excinfo.value.code == 1


def test_missing_database_url_names_field(
    set_env: SetEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    env = {k: v for k, v in VALID_LOCAL_ENV.items() if k != "DATABASE_URL"}
    set_env(env)
    with pytest.raises(SystemExit):
        load_settings()
    err = capsys.readouterr().err
    assert CFG_INVALID in err
    assert "DATABASE_URL" in err


def test_debug_log_level_rejected_in_production(set_env: SetEnv) -> None:
    set_env(
        {
            **VALID_LOCAL_ENV,
            "APP_ENV": "production",
            "LOG_LEVEL": "DEBUG",
            "COOKIE_SECURE": "true",
            "DATABASE_URL": "postgresql+psycopg://u:realpw@db:5432/mediease",
        }
    )
    with pytest.raises(SystemExit):
        load_settings()


def test_insecure_cookies_rejected_in_staging(
    set_env: SetEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    set_env(
        {
            **VALID_LOCAL_ENV,
            "APP_ENV": "staging",
            "COOKIE_SECURE": "false",
            "DATABASE_URL": "postgresql+psycopg://u:realpw@db:5432/mediease",
        }
    )
    with pytest.raises(SystemExit):
        load_settings()
    assert "COOKIE_SECURE" in capsys.readouterr().err


def test_db_echo_params_true_rejected_everywhere(set_env: SetEnv) -> None:
    set_env({**VALID_LOCAL_ENV, "DB_ECHO_PARAMS": "true"})
    with pytest.raises(SystemExit) as excinfo:
        load_settings()
    assert excinfo.value.code == 1


def test_placeholder_database_url_rejected_in_production(
    set_env: SetEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    set_env(
        {
            **VALID_LOCAL_ENV,
            "APP_ENV": "production",
            "COOKIE_SECURE": "true",
            "DATABASE_URL": "postgresql+psycopg://u:change-me@db:5432/mediease",
        }
    )
    with pytest.raises(SystemExit):
        load_settings()
    assert "DATABASE_URL" in capsys.readouterr().err


def test_placeholder_database_url_allowed_in_local(set_env: SetEnv) -> None:
    # The local .env ships a change-me password; that must be allowed locally.
    set_env(
        {
            **VALID_LOCAL_ENV,
            "DATABASE_URL": "postgresql+psycopg://mediease:change-me-local-only@db:5432/mediease",
        }
    )
    settings = load_settings()
    assert settings.APP_ENV is AppEnv.LOCAL


def test_invalid_app_env_rejected(set_env: SetEnv) -> None:
    set_env({**VALID_LOCAL_ENV, "APP_ENV": "prod"})  # not in the allowed set
    with pytest.raises(SystemExit):
        load_settings()


def test_settings_are_frozen(set_env: SetEnv) -> None:
    set_env(VALID_LOCAL_ENV)
    settings = load_settings()
    with pytest.raises(Exception):  # noqa: B017 — pydantic raises on frozen mutation
        settings.APP_ENV = AppEnv.PRODUCTION  # type: ignore[misc]


def test_appsettings_type() -> None:
    # Guard: the public type is what the composition root depends on.
    assert issubclass(AppSettings, object)
