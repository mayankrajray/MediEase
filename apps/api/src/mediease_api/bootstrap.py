"""Composition root — the Flask application factory.

CLAUDE.md ("Composition root"): configuration, logging, adapters, middleware and
routes are wired in exactly one place, with **no import-time side effects**.
Importing this module does nothing; only calling ``create_app(settings)`` builds
an app. This is also the only place that chooses adapters (apps/api/CLAUDE.md).
"""

from __future__ import annotations

import structlog
from flask import Flask

from mediease_api.adapters.db.engine import build_engine
from mediease_api.adapters.db.readiness import SqlAlchemyDatabaseCheck
from mediease_api.config.logging import configure_logging
from mediease_api.config.settings import AppSettings
from mediease_api.delivery.errors import register_error_handlers
from mediease_api.delivery.http.platform import create_platform_blueprint
from mediease_api.delivery.middleware import register_request_middleware
from mediease_api.ports.readiness import DatabaseCheck

logger = structlog.get_logger(__name__)


def create_app(settings: AppSettings, *, database_check: DatabaseCheck | None = None) -> Flask:
    """Build and wire the Flask application from validated settings.

    ``database_check`` replaces the real PostgreSQL check, for tests. Building
    the engine opens no connection, so this stays cheap and side-effect free.
    """
    configure_logging(settings)

    if database_check is None:
        database_check = SqlAlchemyDatabaseCheck(build_engine(settings))

    app = Flask(__name__)
    # Keep the validated settings on the app for handlers that need them later.
    app.config["SETTINGS"] = settings

    # Order matters: request context is bound before routes run; error handlers
    # wrap everything so failures still carry the request_id.
    register_request_middleware(app)
    register_error_handlers(app)
    app.register_blueprint(create_platform_blueprint(database_check))

    logger.info("app.created", app_env=settings.APP_ENV.value)
    return app
