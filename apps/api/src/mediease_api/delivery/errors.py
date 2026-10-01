"""HTTP error handling — the stable error envelope (CLAUDE.md "Observability").

Every API error returns:

    { "error": { "code", "message", "request_id", "details" } }

Codes are catalogued in ``docs/ERRORS.md``. Unhandled exceptions become a single
``SYS_UNEXPECTED`` 500 with no stack trace in the body (the trace is logged
server-side, keyed by ``request_id``, so a failure is traceable without leaking
internals to the client).
"""

from __future__ import annotations

from typing import Any

import structlog
from flask import Flask, jsonify
from flask import Response as FlaskResponse
from werkzeug.exceptions import HTTPException

from mediease_api.delivery.middleware import get_request_id

logger = structlog.get_logger(__name__)

SYS_UNEXPECTED = "SYS_UNEXPECTED"


def error_response(
    code: str,
    message: str,
    status: int,
    details: dict[str, Any] | None = None,
) -> tuple[FlaskResponse, int]:
    """Build a response in the stable error envelope."""
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(),
            "details": details or {},
        }
    }
    return jsonify(body), status


def register_error_handlers(app: Flask) -> None:
    """Attach the HTTP-exception and catch-all handlers to the app."""

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException) -> tuple[FlaskResponse, int]:
        # Map werkzeug's HTTP errors (404, 405, …) into the envelope. The code is
        # the uppercased werkzeug name (e.g. NOT_FOUND) so clients get a stable
        # token rather than prose.
        code = (exc.name or "HTTP_ERROR").upper().replace(" ", "_")
        status = exc.code or 500
        logger.info("http.error", code=code, status=status)
        return error_response(code, exc.description or exc.name or "HTTP error", status)

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception) -> tuple[FlaskResponse, int]:
        # Log the full exception server-side (with traceback), return a generic
        # body. The request_id ties the client-visible error to the server log.
        logger.error("app.unexpected_error", code=SYS_UNEXPECTED, exc_info=exc)
        return error_response(
            SYS_UNEXPECTED,
            "An unexpected error occurred.",
            500,
        )
