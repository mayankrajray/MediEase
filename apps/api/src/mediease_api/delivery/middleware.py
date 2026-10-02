"""Request correlation and access logging (CLAUDE.md "One request, one ID").

For every request:

* Accept an inbound ``X-Request-ID`` if it is 1-64 safe characters, otherwise
  generate a ULID.
* Bind it into structlog contextvars so every log line for the request has it.
* Echo it in the ``X-Request-ID`` response header (also on error responses).
* Emit one ``http.access`` event with ``method``, ``route``, ``status`` and
  ``duration_ms``.
"""

from __future__ import annotations

import re
import time

import structlog
from flask import Flask, Response, g, has_app_context, request
from structlog.contextvars import bind_contextvars, clear_contextvars
from ulid import ULID

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LEN = 64

# Letters, digits and . _ : - only. The ID is written into logs and headers, so
# anything else (spaces, quotes, control characters) is replaced, not trusted.
_SAFE_REQUEST_ID = re.compile(rf"[A-Za-z0-9._:\-]{{1,{MAX_REQUEST_ID_LEN}}}")


def get_request_id() -> str | None:
    """Return the current request's ID, or None outside a request."""
    if not has_app_context():
        return None
    request_id = g.get("request_id")
    return request_id if isinstance(request_id, str) else None


def _resolve_request_id() -> str:
    """Use a valid inbound header, otherwise generate a fresh ULID."""
    inbound = request.headers.get(REQUEST_ID_HEADER, "").strip()
    if _SAFE_REQUEST_ID.fullmatch(inbound):
        return inbound
    return str(ULID())


def register_request_middleware(app: Flask) -> None:
    """Attach before/after/teardown hooks for correlation and access logs."""

    @app.before_request
    def _bind_request_context() -> None:
        g.request_id = _resolve_request_id()
        g.request_started = time.perf_counter()
        clear_contextvars()
        bind_contextvars(request_id=g.request_id)

    @app.after_request
    def _echo_and_log(response: Response) -> Response:
        request_id = get_request_id()
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        started = g.get("request_started")
        duration_ms = round((time.perf_counter() - started) * 1000, 2) if started else None
        logger.info(
            "http.access",
            method=request.method,
            # The route template (e.g. /patients/<id>), never the raw path, so
            # identifiers in URLs do not end up in logs.
            route=request.url_rule.rule if request.url_rule else None,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    @app.teardown_request
    def _clear_context(_: BaseException | None = None) -> None:
        clear_contextvars()
