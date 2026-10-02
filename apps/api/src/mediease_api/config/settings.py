"""Typed application settings — the single source of truth for configuration.

CLAUDE.md ("single source of truth for configuration", "fail fast and loudly"):
all configuration is loaded once into a typed, validated ``AppSettings`` object.
No other module reads ``os.environ``. Invalid or missing configuration stops the
process at start-up — never deep inside a request.

Only the settings the API reads today are defined here. Later phases add their
own fields when they first need them, matching the variables documented in
``.env.example`` (CLAUDE.md "introduce technology only when a concrete feature
requires it").
"""

from __future__ import annotations

import sys
from enum import StrEnum
from typing import Literal

import structlog
from pydantic import Field, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

# Stable error code emitted when configuration is invalid (see docs/ERRORS.md).
CFG_INVALID = "CFG_INVALID"

# Placeholder marker used in .env.example; rejected outside APP_ENV=local.
_PLACEHOLDER = "change-me"


class AppEnv(StrEnum):
    """Deployment environment. Drives environment-specific validation."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_deployed(self) -> bool:
        """True for environments that must meet production-grade safety rules."""
        return self in (AppEnv.STAGING, AppEnv.PRODUCTION)


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


def _app_env(info: ValidationInfo) -> AppEnv | None:
    """APP_ENV as already validated, or None if it was itself invalid.

    Fields are validated in declaration order, so every field declared after
    APP_ENV can read it here. When APP_ENV is invalid, its own error is reported
    and environment-dependent rules are skipped rather than guessed.
    """
    value = info.data.get("APP_ENV")
    return value if isinstance(value, AppEnv) else None


class AppSettings(BaseSettings):
    """Validated application configuration.

    Field names map 1:1 to the environment variables in ``.env.example``.
    Each rule is a field validator so a failure is reported against the field
    that must change (``config.invalid`` lists them in ``invalid_fields``).
    """

    model_config = SettingsConfigDict(
        env_file=None,  # the process environment is the source; compose loads .env
        case_sensitive=True,
        extra="ignore",  # variables for later milestones are not errors here
        frozen=True,
    )

    # Declaration order matters: APP_ENV must come first (see _app_env).
    APP_ENV: AppEnv = AppEnv.LOCAL
    LOG_LEVEL: LogLevel = "INFO"
    # SQL parameter logging. Must stay false everywhere (parameters can hold patient data).
    DB_ECHO_PARAMS: bool = False
    # Required from M0-P2 so a missing value fails at start-up, not at the first query.
    DATABASE_URL: str = Field(min_length=1)
    # false only for local http; must be true anywhere served over https.
    COOKIE_SECURE: bool = False

    @field_validator("LOG_LEVEL")
    @classmethod
    def _no_debug_when_deployed(cls, value: str, info: ValidationInfo) -> str:
        env = _app_env(info)
        if env is not None and env.is_deployed and value == "DEBUG":
            raise ValueError(f"must not be DEBUG when APP_ENV={env.value}")
        return value

    @field_validator("DB_ECHO_PARAMS")
    @classmethod
    def _echo_params_always_off(cls, value: bool) -> bool:
        if value:
            raise ValueError(
                "must be false in every environment (SQL parameters may hold patient data)"
            )
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def _no_placeholder_outside_local(cls, value: str, info: ValidationInfo) -> str:
        env = _app_env(info)
        if env is not None and env is not AppEnv.LOCAL and _PLACEHOLDER in value:
            raise ValueError(
                f"contains a '{_PLACEHOLDER}' placeholder; set a real value for APP_ENV={env.value}"
            )
        return value

    @field_validator("COOKIE_SECURE")
    @classmethod
    def _secure_cookies_when_deployed(cls, value: bool, info: ValidationInfo) -> bool:
        env = _app_env(info)
        if env is not None and env.is_deployed and not value:
            raise ValueError(f"must be true when APP_ENV={env.value}")
        return value


def load_settings() -> AppSettings:
    """Load and validate settings, or exit the process with a clear message.

    The only entry point the composition root uses. On failure it logs a
    structured ``config.invalid`` event naming the offending field(s) and exits
    with status 1 (``CFG_INVALID``). Input values are never echoed, so secrets
    in a malformed variable do not reach the log.
    """
    try:
        return AppSettings()  # type: ignore[call-arg]  # values come from the environment
    except ValidationError as exc:
        fields = sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]})
        detail = _summarise(exc)
        logger.error(
            "config.invalid",
            code=CFG_INVALID,
            invalid_fields=fields,
            error_count=exc.error_count(),
            detail=detail,
        )
        # Plain stderr line as well: logging may not be configured yet, and an
        # operator reading `docker compose logs` should see the cause immediately.
        print(
            f"[{CFG_INVALID}] Invalid configuration in field(s): {', '.join(fields)}. {detail}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _summarise(exc: ValidationError) -> str:
    """Human-readable summary of validation errors without input values."""
    return " | ".join(
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}" for err in exc.errors()
    )
