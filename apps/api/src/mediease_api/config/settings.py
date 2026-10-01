"""Typed application settings — the single source of truth for configuration.

CLAUDE.md ("single source of truth for configuration", "fail fast and loudly"):
all configuration is loaded once into a typed, validated ``AppSettings`` object.
No other module reads ``os.environ``. Invalid or missing configuration stops the
process at start-up — never deep inside a request.

Only the settings that M0-P2/M0-P3 actually use are defined here. Later
milestones add their own fields in the phase that first needs them, matching the
documented variables in ``.env.example`` (CLAUDE.md "introduce technology only
when a concrete feature requires it").
"""

from __future__ import annotations

import sys
from enum import StrEnum
from typing import Literal

import structlog
from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

# Stable error code emitted when configuration is invalid (see docs/ERRORS.md).
CFG_INVALID = "CFG_INVALID"

# Placeholder marker used in .env.example. Rejected outside local.
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


class ConfigError(Exception):
    """Raised when configuration fails validation. Carries the stable code."""

    code = CFG_INVALID


class AppSettings(BaseSettings):
    """Validated application configuration.

    Field names map 1:1 to the environment variables documented in
    ``.env.example``. Validation enforces the rules in
    ``docs/milestones/M0-foundation.md``.
    """

    model_config = SettingsConfigDict(
        env_file=None,  # the process environment is the source; compose/.env load it
        case_sensitive=True,
        extra="ignore",  # later-milestone vars in .env are not errors here
        frozen=True,
    )

    # --- Application ---------------------------------------------------------
    APP_ENV: AppEnv = AppEnv.LOCAL
    LOG_LEVEL: LogLevel = "INFO"
    # SQL parameter logging. Must stay false everywhere (never log patient data).
    DB_ECHO_PARAMS: bool = False

    # --- Database (read by the engine in M0-P3; required from M0-P2 on) ------
    DATABASE_URL: str = Field(min_length=1)

    # --- Auth / sessions -----------------------------------------------------
    # false only for local http; must be true anywhere served over https.
    COOKIE_SECURE: bool = False

    # --- Service wiring ------------------------------------------------------
    API_PORT: int = Field(default=8000, ge=1, le=65535)

    @field_validator("DATABASE_URL")
    @classmethod
    def _database_url_not_placeholder(cls, value: str) -> str:
        if _PLACEHOLDER in value:
            # The password in the local URL is a placeholder; allowed only when
            # APP_ENV=local. The cross-field check in _enforce_env_rules runs
            # after this, so defer the environment-aware decision to there by
            # leaving the value intact here and validating placeholders centrally.
            return value
        return value

    @model_validator(mode="after")
    def _enforce_env_rules(self) -> AppSettings:
        """Cross-field, environment-specific rules (fail fast)."""
        errors: list[str] = []

        # DB_ECHO_PARAMS must be false in every environment.
        if self.DB_ECHO_PARAMS:
            errors.append(
                "DB_ECHO_PARAMS must be false in every environment "
                "(SQL parameters may contain patient data)"
            )

        if self.APP_ENV.is_deployed:
            if not self.COOKIE_SECURE:
                errors.append(f"COOKIE_SECURE must be true when APP_ENV={self.APP_ENV.value}")
            if self.LOG_LEVEL == "DEBUG":
                errors.append(f"LOG_LEVEL must not be DEBUG when APP_ENV={self.APP_ENV.value}")
            # Reject leftover placeholder secrets in deployed environments.
            if _PLACEHOLDER in self.DATABASE_URL:
                errors.append(
                    f"DATABASE_URL still contains a '{_PLACEHOLDER}' placeholder "
                    f"when APP_ENV={self.APP_ENV.value}"
                )

        if errors:
            # Raise a single ValueError so pydantic wraps it; load_settings turns
            # the ValidationError into a clear, field-named failure.
            raise ValueError("; ".join(errors))
        return self


def load_settings() -> AppSettings:
    """Load and validate settings, or exit the process with a clear message.

    This is the only entry point the composition root uses. On failure it logs a
    structured ``config.invalid`` event naming the offending field(s) and exits
    non-zero (``CFG_INVALID``) — misconfiguration never reaches a request.
    """
    try:
        return AppSettings()  # type: ignore[call-arg]  # values come from the environment
    except ValidationError as exc:
        fields = sorted({str(err["loc"][0]) if err["loc"] else "<root>" for err in exc.errors()})
        logger.error(
            "config.invalid",
            code=CFG_INVALID,
            invalid_fields=fields,
            error_count=len(exc.errors()),
            detail=_summarise(exc),
        )
        # Last-resort stderr message in case logging is not yet configured.
        print(
            f"[{CFG_INVALID}] Invalid configuration in field(s): {', '.join(fields)}. "
            f"{_summarise(exc)}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def _summarise(exc: ValidationError) -> str:
    """Human-readable, secret-free summary of validation errors."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return " | ".join(parts)
