"""Composition root — the Flask application factory.

CLAUDE.md ("Composition root"): configuration, logging, adapters, middleware and
routes are wired in exactly one place, with **no import-time side effects**.
Importing this module does nothing; only calling ``create_app(settings)`` builds
an app. This is also the only place that chooses adapters (apps/api/CLAUDE.md).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

import structlog
from flask import Flask
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.engine import build_engine
from mediease_api.adapters.db.readiness import SqlAlchemyDatabaseCheck
from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork, build_session_factory
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.security.argon2_hasher import Argon2PasswordHasher
from mediease_api.adapters.security.jwt_tokens import JwtAccessTokenIssuer
from mediease_api.adapters.security.refresh_secrets import Sha256RefreshTokenSecrets
from mediease_api.application.auth._session import SessionIssuer
from mediease_api.application.auth.refresh_session import RefreshSession
from mediease_api.application.auth.sign_in import SignIn
from mediease_api.application.auth.sign_out import SignOut
from mediease_api.config.logging import configure_logging
from mediease_api.config.settings import AppSettings
from mediease_api.delivery.errors import register_error_handlers
from mediease_api.delivery.http.auth import create_auth_blueprint
from mediease_api.delivery.http.csrf import register_csrf_protection
from mediease_api.delivery.http.platform import create_platform_blueprint
from mediease_api.delivery.middleware import register_request_middleware
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.readiness import DatabaseCheck
from mediease_api.ports.security import PasswordHasher

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _AuthUseCases:
    """Builds the auth use cases with a fresh unit of work for each request."""

    session_factory: sessionmaker[Session]
    clock: ClockPort
    ids: Uuid7Generator
    hasher: PasswordHasher
    refresh_secrets: Sha256RefreshTokenSecrets
    sessions: SessionIssuer
    dummy_password_hash: str

    def sign_in(self) -> SignIn:
        return SignIn(
            uow=SqlAlchemyUnitOfWork(self.session_factory),
            clock=self.clock,
            ids=self.ids,
            hasher=self.hasher,
            sessions=self.sessions,
            dummy_password_hash=self.dummy_password_hash,
        )

    def refresh(self) -> RefreshSession:
        return RefreshSession(
            uow=SqlAlchemyUnitOfWork(self.session_factory),
            clock=self.clock,
            secrets=self.refresh_secrets,
            sessions=self.sessions,
        )

    def sign_out(self) -> SignOut:
        return SignOut(
            uow=SqlAlchemyUnitOfWork(self.session_factory),
            clock=self.clock,
            secrets=self.refresh_secrets,
        )


def build_password_hasher() -> PasswordHasher:
    """Production Argon2id parameters (also used by ``make seed``)."""
    return Argon2PasswordHasher()


def create_app(
    settings: AppSettings,
    *,
    database_check: DatabaseCheck | None = None,
    password_hasher: PasswordHasher | None = None,
    clock: ClockPort | None = None,
) -> Flask:
    """Build and wire the Flask application from validated settings.

    The keyword arguments replace adapters in tests: a fake readiness check, a
    cheap password hasher, a fixed clock. Building the engine opens no
    connection, so this stays side-effect free.
    """
    configure_logging(settings)

    engine = build_engine(settings)
    if database_check is None:
        database_check = SqlAlchemyDatabaseCheck(engine)

    clock = clock or SystemClock()
    ids = Uuid7Generator()
    hasher = password_hasher or build_password_hasher()
    refresh_secrets = Sha256RefreshTokenSecrets()
    auth_use_cases = _AuthUseCases(
        session_factory=build_session_factory(engine),
        clock=clock,
        ids=ids,
        hasher=hasher,
        refresh_secrets=refresh_secrets,
        sessions=SessionIssuer(
            ids=ids,
            secrets=refresh_secrets,
            access_tokens=JwtAccessTokenIssuer(
                signing_key=settings.JWT_SIGNING_KEY.get_secret_value(),
                ttl=timedelta(seconds=settings.ACCESS_TOKEN_TTL_SECONDS),
                ids=ids,
            ),
            refresh_ttl=timedelta(seconds=settings.REFRESH_TOKEN_TTL_SECONDS),
        ),
        # One real hash of a random password, so unknown accounts cost the
        # same verification as real ones (spec R2).
        dummy_password_hash=hasher.hash(secrets.token_urlsafe(32)),
    )

    app = Flask(__name__)
    # Keep the validated settings on the app for handlers that need them later.
    app.config["SETTINGS"] = settings

    # Order matters: request context is bound first, then CSRF is checked
    # before any route runs; error handlers wrap everything so failures still
    # carry the request_id.
    register_request_middleware(app)
    register_csrf_protection(app)
    register_error_handlers(app)
    app.register_blueprint(create_platform_blueprint(database_check))
    app.register_blueprint(
        create_auth_blueprint(auth_use_cases, cookie_secure=settings.COOKIE_SECURE)
    )

    logger.info("app.created", app_env=settings.APP_ENV.value)
    return app
