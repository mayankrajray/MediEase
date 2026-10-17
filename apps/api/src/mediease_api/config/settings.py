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

import re
import sys
from enum import StrEnum
from typing import Literal

import structlog
from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

# Stable error code emitted when configuration is invalid (see docs/ERRORS.md).
CFG_INVALID = "CFG_INVALID"

# Placeholder marker used in .env.example; rejected outside APP_ENV=local.
_PLACEHOLDER = "change-me"

# SQLAlchemy URL scheme for PostgreSQL through psycopg 3 (ADR-0004).
_DATABASE_URL_PREFIX = "postgresql+psycopg://"

_MIN_SIGNING_KEY_LENGTH = 32

# M4-P5: patient link keys. The development key is used only when none is set in local or test.
_LINK_KEY_ID = re.compile(r"[A-Za-z0-9_-]{1,16}")
_DEV_LINK_KEY = "dev:change-me-local-only-patient-link-key-0001"


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
BlobBackend = Literal["local", "s3"]


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
    # Where the web app lives, used to build links we hand to people (staff
    # invitations from M1-P5, patient links from M4).
    PUBLIC_BASE_URL: str = "http://localhost:3000"
    # HS256 key for access tokens (M1-P2). Never logged: SecretStr hides it from repr.
    JWT_SIGNING_KEY: SecretStr
    # HMAC key for the IP fingerprints in audit events (M1-P4). Separate from the
    # JWT key so either can be rotated alone; rotating it makes older
    # fingerprints incomparable, which is the accepted trade-off.
    AUDIT_IP_SALT: SecretStr
    # Access token lifetime: 15 min by default (spec R4); 1-60 minutes allowed.
    ACCESS_TOKEN_TTL_SECONDS: int = Field(default=900, ge=60, le=3600)
    # Refresh token lifetime: 14 days by default (spec R4); 1 hour to 30 days allowed.
    REFRESH_TOKEN_TTL_SECONDS: int = Field(default=1_209_600, ge=3600, le=2_592_000)
    # Generated files such as prescription PDFs (M4-P4, ADR-0012). `local`: a directory (the
    # compose volume `blobs`); `s3`: an S3-compatible bucket, credentials from the standard
    # AWS chain (environment or instance role), never from these settings.
    BLOB_STORAGE: BlobBackend = "local"
    BLOB_LOCAL_DIR: str = Field(default="/var/lib/mediease/blobs", min_length=1)
    S3_BUCKET: str = ""
    S3_REGION: str = "ap-south-1"
    # Empty for AWS itself; the endpoint of another S3-compatible store otherwise.
    S3_ENDPOINT_URL: str = ""
    # Patient link keys (M4-P5, spec R9): "kid:secret,kid:secret"; the first signs, all verify.
    # Empty in local and test means a fixed development key; required when deployed.
    PATIENT_LINK_SIGNING_KEYS: SecretStr = SecretStr("")
    PATIENT_LINK_TTL_DAYS: int = Field(default=90, ge=1, le=90)

    @field_validator("PATIENT_LINK_SIGNING_KEYS")
    @classmethod
    def _link_keys(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        env = _app_env(info)
        raw = value.get_secret_value().strip()
        if not raw:
            if env is not None and env.is_deployed:
                raise ValueError(f"is required when APP_ENV={env.value}")
            return SecretStr(_DEV_LINK_KEY)
        seen: set[str] = set()
        for pair in raw.split(","):
            kid, sep, secret = pair.strip().partition(":")
            if not sep or not _LINK_KEY_ID.fullmatch(kid):
                raise ValueError("must be kid:secret pairs; a kid is 1-16 letters, digits, - or _")
            if kid in seen:
                raise ValueError("names a key ID twice")
            seen.add(kid)
            placeholder = _PLACEHOLDER in secret
            if placeholder and env is not AppEnv.LOCAL and env is not AppEnv.TEST:
                raise ValueError(f"contains a '{_PLACEHOLDER}' placeholder; set real keys")
            if not placeholder and len(secret) < _MIN_SIGNING_KEY_LENGTH:
                raise ValueError(
                    f"each secret must be at least {_MIN_SIGNING_KEY_LENGTH} characters"
                )
        return SecretStr(raw)

    def patient_link_keys(self) -> dict[str, bytes]:
        """The keys in order, the signing key first (``HmacLinkSigner``)."""
        keys: dict[str, bytes] = {}
        for pair in self.PATIENT_LINK_SIGNING_KEYS.get_secret_value().split(","):
            kid, _, secret = pair.strip().partition(":")
            keys[kid] = secret.encode("utf-8")
        return keys

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
    def _psycopg_driver(cls, value: str) -> str:
        # A bare postgresql:// URL makes SQLAlchemy load psycopg2, which is not
        # installed; catch it at start-up with a clear message instead.
        if not value.startswith(_DATABASE_URL_PREFIX):
            raise ValueError(f"must start with '{_DATABASE_URL_PREFIX}' (psycopg 3 driver)")
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

    @field_validator("PUBLIC_BASE_URL")
    @classmethod
    def _absolute_public_url(cls, value: str, info: ValidationInfo) -> str:
        # Links built from it are sent to people, so a relative or empty value
        # would produce a dead link rather than an obvious failure.
        if not value.startswith(("http://", "https://")):
            raise ValueError("must be an absolute http(s) URL")
        env = _app_env(info)
        if env is not None and env.is_deployed and value.startswith("http://"):
            raise ValueError(f"must use https when APP_ENV={env.value}")
        return value.rstrip("/")

    @field_validator("JWT_SIGNING_KEY")
    @classmethod
    def _strong_signing_key(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        key = value.get_secret_value()
        # HS256 produces a 256-bit tag; a shorter key is the weakest link.
        if len(key) < _MIN_SIGNING_KEY_LENGTH:
            raise ValueError(f"must be at least {_MIN_SIGNING_KEY_LENGTH} characters")
        env = _app_env(info)
        if env is not None and env is not AppEnv.LOCAL and _PLACEHOLDER in key:
            raise ValueError(
                f"contains a '{_PLACEHOLDER}' placeholder; set a real value for APP_ENV={env.value}"
            )
        return value

    @field_validator("S3_BUCKET")
    @classmethod
    def _bucket_for_s3(cls, value: str, info: ValidationInfo) -> str:
        if info.data.get("BLOB_STORAGE") == "s3" and not value.strip():
            raise ValueError("is required when BLOB_STORAGE=s3")
        return value.strip()

    @field_validator("S3_ENDPOINT_URL")
    @classmethod
    def _absolute_endpoint(cls, value: str) -> str:
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("must be an absolute http(s) URL or empty")
        return value

    @field_validator("AUDIT_IP_SALT")
    @classmethod
    def _strong_audit_salt(cls, value: SecretStr, info: ValidationInfo) -> SecretStr:
        # Same strength rules as the signing key: it keys an HMAC-SHA256.
        return cls._strong_signing_key(value, info)


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
