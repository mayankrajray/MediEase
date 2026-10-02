"""HTTP error handling — the stable error envelope (CLAUDE.md "Observability").

Every API error returns:

    { "error": { "code", "message", "request_id", "details" } }

Codes are catalogued in ``docs/ERRORS.md``. Readiness failures become a 503 with
their ``READY_*`` code. Unhandled exceptions become a single
``SYS_UNEXPECTED`` 500 with no stack trace in the body; the trace is logged
server-side with the same ``request_id``, so the failure is traceable without
leaking internals to the client.
"""

from __future__ import annotations

import re
from typing import Any

import structlog
from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException

from mediease_api.delivery.middleware import get_request_id
from mediease_api.ports.readiness import DatabaseTimeout, DatabaseUnavailable, ReadinessError

logger = structlog.get_logger(__name__)

SYS_UNEXPECTED = "SYS_UNEXPECTED"
_SYS_UNEXPECTED_MESSAGE = "An unexpected error occurred."

# Safe to show to staff and to monitoring; details live in the server log.
_READINESS_MESSAGES = {
    DatabaseUnavailable.code: "The database is not reachable.",
    DatabaseTimeout.code: "The database did not respond in time.",
}

# Framework HTTP errors with a catalogued code. Any other 4xx becomes
# REQ_<WERKZEUG_NAME> (e.g. REQ_UNSUPPORTED_MEDIA_TYPE); see docs/ERRORS.md.
_HTTP_CODES = {
    404: "REQ_NOT_FOUND",
    405: "REQ_METHOD_NOT_ALLOWED",
}

# Werkzeug headers worth keeping on the envelope response (405 must say what is allowed).
_PRESERVED_HEADERS = ("Allow", "Retry-After")


def error_response(
    code: str,
    message: str,
    status: int,
    details: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    """Build a response in the stable error envelope."""
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(),
            "details": details or {},
        }
    }
    return jsonify(body), status


def _http_error_code(exc: HTTPException) -> str:
    status = exc.code or 500
    if status in _HTTP_CODES:
        return _HTTP_CODES[status]
    name = re.sub(r"[^A-Z0-9]+", "_", (exc.name or "HTTP error").upper()).strip("_")
    return f"REQ_{name}"


def register_error_handlers(app: Flask) -> None:
    """Attach the readiness, HTTP-exception and catch-all handlers to the app."""

    @app.errorhandler(ReadinessError)
    def _handle_readiness_error(exc: ReadinessError) -> tuple[Response, int]:
        # Degraded but handled (WARNING): the instance reports not-ready and the
        # orchestrator stops routing to it. The cause's type is logged for
        # diagnosis; its message is not (driver messages name hosts and users).
        cause = exc.__cause__
        logger.warning(
            "ready.check_failed",
            code=exc.code,
            cause=type(cause).__name__ if cause else None,
        )
        return error_response(exc.code, _READINESS_MESSAGES[exc.code], 503)

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException) -> tuple[Response, int]:
        status = exc.code or 500
        if status >= 500:
            # A framework-raised 5xx is still a server fault: same code and
            # generic message as an unhandled exception.
            logger.error("http.server_error", code=SYS_UNEXPECTED, status=status)
            return error_response(SYS_UNEXPECTED, _SYS_UNEXPECTED_MESSAGE, status)

        code = _http_error_code(exc)
        logger.info("http.client_error", code=code, status=status)
        response, _ = error_response(code, exc.description or exc.name, status)
        for name, value in exc.get_headers():
            if name in _PRESERVED_HEADERS:
                response.headers[name] = value
        return response, status

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception) -> tuple[Response, int]:
        logger.error("app.unexpected_error", code=SYS_UNEXPECTED, exc_info=exc)
        return error_response(SYS_UNEXPECTED, _SYS_UNEXPECTED_MESSAGE, 500)
