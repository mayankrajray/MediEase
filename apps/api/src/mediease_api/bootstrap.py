"""Composition root — the Flask application factory.

CLAUDE.md ("Composition root"): configuration, logging, middleware and routes
are wired in exactly one place, with **no import-time side effects**. Importing
this module does nothing; only calling ``create_app(settings)`` builds an app.
Tests construct an app with explicit settings; ``wsgi`` builds one from the
environment.
"""

from __future__ import annotations

import structlog
from flask import Flask

from mediease_api.config.logging import configure_logging
from mediease_api.config.settings import AppSettings
from mediease_api.delivery.errors import register_error_handlers
from mediease_api.delivery.http.platform import platform_bp
from mediease_api.delivery.middleware import register_request_middleware

logger = structlog.get_logger(__name__)


def create_app(settings: AppSettings) -> Flask:
    """Build and wire the Flask application from validated settings."""
    configure_logging(settings)

    app = Flask(__name__)
    # Keep the validated settings on the app for handlers that need them later.
    app.config["SETTINGS"] = settings

    # Order matters: request context is bound before routes run; error handlers
    # wrap everything so failures still carry the request_id.
    register_request_middleware(app)
    register_error_handlers(app)
    app.register_blueprint(platform_bp)

    logger.info("app.created", app_env=settings.APP_ENV.value)
    return app
