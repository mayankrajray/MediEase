"""Unit tests for typed settings (NFR-12 — fail fast on misconfiguration).

Acceptance criteria from docs/milestones/M0-foundation.md: a valid config
loads; a missing DATABASE_URL, DEBUG in production, insecure cookies in staging
and DB_ECHO_PARAMS=true each stop start-up with CFG_INVALID naming the field.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mediease_api.config.settings import CFG_INVALID, AppEnv, AppSettings, load_settings
from tests.conftest import TEST_IP_SALT, TEST_SIGNING_KEY, SetEnv


def _invalid_fields(env: dict[str, str], set_env: SetEnv) -> set[str]:
    """Load settings expecting failure; return the names of the rejected fields."""
    set_env(env)
    with pytest.raises(ValidationError) as excinfo:
        AppSettings()  # type: ignore[call-arg]
    return {str(err["loc"][0]) for err in excinfo.value.errors()}


def test_nfr_12_valid_config_loads(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    set_env(valid_env)
    settings = load_settings()
    assert settings.APP_ENV is AppEnv.TEST
    assert settings.LOG_LEVEL == "INFO"
    assert settings.DB_ECHO_PARAMS is False
    assert settings.COOKIE_SECURE is False


def test_nfr_12_defaults_apply_when_optional_vars_absent(set_env: SetEnv) -> None:
    set_env(
        {
            "DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/db",
            "JWT_SIGNING_KEY": TEST_SIGNING_KEY,
            "AUDIT_IP_SALT": TEST_IP_SALT,
        }
    )
    settings = load_settings()
    assert settings.APP_ENV is AppEnv.LOCAL
    assert settings.LOG_LEVEL == "INFO"
    assert settings.ACCESS_TOKEN_TTL_SECONDS == 900
    assert settings.REFRESH_TOKEN_TTL_SECONDS == 14 * 24 * 3600


def test_nfr_12_missing_database_url_exits_naming_the_field(
    set_env: SetEnv, valid_env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    del valid_env["DATABASE_URL"]
    set_env(valid_env)
    with pytest.raises(SystemExit) as excinfo:
        load_settings()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert CFG_INVALID in err
    assert "DATABASE_URL" in err


def test_nfr_12_debug_rejected_in_production(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    env = {**valid_env, "APP_ENV": "production", "LOG_LEVEL": "DEBUG", "COOKIE_SECURE": "true"}
    assert _invalid_fields(env, set_env) == {"LOG_LEVEL"}


def test_nfr_12_debug_allowed_in_local(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    set_env({**valid_env, "APP_ENV": "local", "LOG_LEVEL": "DEBUG"})
    assert load_settings().LOG_LEVEL == "DEBUG"


def test_nfr_12_insecure_cookies_rejected_in_staging(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    env = {**valid_env, "APP_ENV": "staging", "COOKIE_SECURE": "false"}
    assert _invalid_fields(env, set_env) == {"COOKIE_SECURE"}


@pytest.mark.parametrize("app_env", ["local", "test", "staging", "production"])
def test_nfr_12_db_echo_params_rejected_in_every_environment(
    app_env: str, set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    env = {**valid_env, "APP_ENV": app_env, "COOKIE_SECURE": "true", "DB_ECHO_PARAMS": "true"}
    assert _invalid_fields(env, set_env) == {"DB_ECHO_PARAMS"}


@pytest.mark.parametrize("app_env", ["test", "staging", "production"])
def test_nfr_12_placeholder_rejected_outside_local(
    app_env: str, set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    env = {
        **valid_env,
        "APP_ENV": app_env,
        "COOKIE_SECURE": "true",
        "DATABASE_URL": "postgresql+psycopg://mediease:change-me@db:5432/mediease",
    }
    assert _invalid_fields(env, set_env) == {"DATABASE_URL"}


def test_nfr_12_placeholder_allowed_in_local(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    # .env.example ships a change-me password so `cp .env.example .env` works locally.
    url = "postgresql+psycopg://mediease:change-me-local-only@db:5432/mediease"
    set_env({**valid_env, "APP_ENV": "local", "DATABASE_URL": url})
    assert url == load_settings().DATABASE_URL


def test_nfr_12_unknown_app_env_rejected(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    assert _invalid_fields({**valid_env, "APP_ENV": "prod"}, set_env) == {"APP_ENV"}


@pytest.mark.parametrize(
    "url",
    ["postgresql://u:p@db:5432/mediease", "sqlite:///mediease.db", "not-a-url"],
    ids=["psycopg2-default", "other-database", "garbage"],
)
def test_nfr_12_database_url_must_use_psycopg_driver(
    url: str, set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    assert _invalid_fields({**valid_env, "DATABASE_URL": url}, set_env) == {"DATABASE_URL"}


def test_nfr_12_config_invalid_never_echoes_values(
    set_env: SetEnv, valid_env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "postgresql+psycopg://mediease:change-me-SECRET@db:5432/mediease"
    set_env({**valid_env, "APP_ENV": "production", "COOKIE_SECURE": "true", "DATABASE_URL": secret})
    with pytest.raises(SystemExit):
        load_settings()
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err


def test_nfr_12_settings_are_immutable(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    set_env(valid_env)
    settings = load_settings()
    with pytest.raises(ValidationError):
        settings.APP_ENV = AppEnv.PRODUCTION  # type: ignore[misc]


# --- Auth settings (M1-P2) -------------------------------------------------------------


def test_fr_auth_02_signing_key_is_required(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    del valid_env["JWT_SIGNING_KEY"]
    assert _invalid_fields(valid_env, set_env) == {"JWT_SIGNING_KEY"}


def test_fr_auth_02_short_signing_key_is_rejected_everywhere(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    env = {**valid_env, "APP_ENV": "local", "JWT_SIGNING_KEY": "change-me"}
    assert _invalid_fields(env, set_env) == {"JWT_SIGNING_KEY"}


def test_fr_auth_02_placeholder_signing_key_only_in_local(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    placeholder = "change-me-local-only-jwt-signing-key-000"
    set_env({**valid_env, "APP_ENV": "local", "JWT_SIGNING_KEY": placeholder})
    assert load_settings().JWT_SIGNING_KEY.get_secret_value() == placeholder

    env = {**valid_env, "APP_ENV": "production", "COOKIE_SECURE": "true"}
    assert _invalid_fields({**env, "JWT_SIGNING_KEY": placeholder}, set_env) == {"JWT_SIGNING_KEY"}


def test_fr_auth_02_signing_key_never_appears_in_repr_or_errors(
    set_env: SetEnv, valid_env: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    set_env(valid_env)
    assert TEST_SIGNING_KEY not in repr(load_settings())

    set_env({**valid_env, "JWT_SIGNING_KEY": "short-SECRET"})
    with pytest.raises(SystemExit):
        load_settings()
    captured = capsys.readouterr()
    assert "SECRET" not in captured.out + captured.err


# --- Audit settings (M1-P4) ------------------------------------------------------------


def test_fr_aud_01_ip_salt_is_required_and_must_be_strong(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    missing = {k: v for k, v in valid_env.items() if k != "AUDIT_IP_SALT"}
    assert _invalid_fields(missing, set_env) == {"AUDIT_IP_SALT"}
    assert _invalid_fields({**valid_env, "AUDIT_IP_SALT": "change-me"}, set_env) == {
        "AUDIT_IP_SALT"
    }


def test_fr_aud_01_placeholder_ip_salt_only_in_local(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    placeholder = "change-me-local-only-audit-ip-salt-000"
    set_env({**valid_env, "APP_ENV": "local", "AUDIT_IP_SALT": placeholder})
    assert load_settings().AUDIT_IP_SALT.get_secret_value() == placeholder

    env = {**valid_env, "APP_ENV": "production", "COOKIE_SECURE": "true"}
    assert _invalid_fields({**env, "AUDIT_IP_SALT": placeholder}, set_env) == {"AUDIT_IP_SALT"}


def test_fr_aud_01_ip_salt_never_appears_in_repr(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env(valid_env)
    assert TEST_IP_SALT not in repr(load_settings())


# --- Public base URL (M1-P5: invitation links) ------------------------------------------


@pytest.mark.parametrize("value", ["localhost:3000", "", "/invite"])
def test_fr_org_04_public_base_url_must_be_absolute(
    set_env: SetEnv, valid_env: dict[str, str], value: str
) -> None:
    """Links built from it are handed to people, so a relative value is a dead link."""
    assert _invalid_fields({**valid_env, "PUBLIC_BASE_URL": value}, set_env) == {"PUBLIC_BASE_URL"}


def test_public_base_url_must_be_https_when_deployed(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    env = {**valid_env, "APP_ENV": "production", "COOKIE_SECURE": "true"}
    assert _invalid_fields({**env, "PUBLIC_BASE_URL": "http://mediease.example"}, set_env) == {
        "PUBLIC_BASE_URL"
    }
    set_env({**env, "PUBLIC_BASE_URL": "https://mediease.example/"})
    # The trailing slash is dropped, so joined paths never double up.
    assert load_settings().PUBLIC_BASE_URL == "https://mediease.example"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ACCESS_TOKEN_TTL_SECONDS", "30"),
        ("ACCESS_TOKEN_TTL_SECONDS", "7200"),
        ("REFRESH_TOKEN_TTL_SECONDS", "60"),
        ("REFRESH_TOKEN_TTL_SECONDS", "5000000"),
    ],
)
def test_token_lifetimes_are_bounded(
    name: str, value: str, set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    assert _invalid_fields({**valid_env, name: value}, set_env) == {name}


def test_m4_p4_blob_storage_defaults_to_the_local_volume(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    set_env(valid_env)
    settings = load_settings()
    assert settings.BLOB_STORAGE == "local"
    assert settings.BLOB_LOCAL_DIR == "/var/lib/mediease/blobs"


def test_m4_p4_s3_needs_a_bucket_and_an_absolute_endpoint(
    set_env: SetEnv, valid_env: dict[str, str]
) -> None:
    env = {**valid_env, "BLOB_STORAGE": "s3", "S3_ENDPOINT_URL": "minio:9000"}
    assert _invalid_fields(env, set_env) == {"S3_BUCKET", "S3_ENDPOINT_URL"}
    env = {**valid_env, "BLOB_STORAGE": "ftp", "S3_ENDPOINT_URL": ""}
    assert _invalid_fields(env, set_env) == {"BLOB_STORAGE"}


def test_m4_p4_s3_settings_load(set_env: SetEnv, valid_env: dict[str, str]) -> None:
    set_env({**valid_env, "BLOB_STORAGE": "s3", "S3_BUCKET": " mediease-rx "})
    settings = load_settings()
    assert (settings.BLOB_STORAGE, settings.S3_BUCKET) == ("s3", "mediease-rx")
