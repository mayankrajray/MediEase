"""Request correlation and access logging (CLAUDE.md "One request, one ID").

For every request:

* Accept an inbound ``X-Request-ID`` (<= 64 chars) or generate a ULID.
* Bind it (and later ``clinic_id`` / ``user_id``) into structlog contextvars so
  all log lines for the request carry it.
* Echo it back in the ``X-Request-ID`` response header.
* Emit one ``http.access`` log event per request with ``duration_ms``.
"""

from __future__ import annotations

import time

import structlog
from flask import Flask, Response, g, request
from structlog.contextvars import bind_contextvars, clear_contextvars
from ulid import ULID

logger = structlog.get_logger(__name__)

# Guard against unbounded/abusive inbound IDs.
MAX_REQUEST_ID_LEN = 64

_REQUEST_ID_HEADER = "X-Request-ID"
_START_KEY = "_request_start_perf"


def get_request_id() -> str | None:
    """Return the current request's ID, if a request is in scope."""
    return g.get("request_id") if _in_request() else None


def _in_request() -> bool:
    try:
        return bool(g)
    except RuntimeError:
        return False


def _resolve_request_id() -> str:
    """Use a valid inbound header, otherwise generate a fresh ULID."""
    inbound = request.headers.get(_REQUEST_ID_HEADER, "").strip()
    if inbound and len(inbound) <= MAX_REQUEST_ID_LEN:
        return inbound
    return str(ULID())


def register_request_middleware(app: Flask) -> None:
    """Attach before/after/teardown hooks for correlation and access logs."""

    @app.before_request
    def _bind_request_context() -> None:
        request_id = _resolve_request_id()
        g.request_id = request_id
        g.__dict__[_START_KEY] = time.perf_counter()
        clear_contextvars()
        bind_contextvars(request_id=request_id)

    @app.after_request
    def _echo_and_log(response: Response) -> Response:
        response.headers[_REQUEST_ID_HEADER] = g.get("request_id", "")
        start = g.get(_START_KEY)
        duration_ms = round((time.perf_counter() - start) * 1000, 2) if start else None
        logger.info(
            "http.access",
            method=request.method,
            route=request.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    @app.teardown_request
    def _clear_context(_: BaseException | None = None) -> None:
        clear_contextvars()
