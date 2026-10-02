"""CSRF protection by double submit (ADR-0006, ARCHITECTURE.md §9).

Every unsafe request (anything but GET/HEAD/OPTIONS) under ``/api/`` that
carries a session cookie must send ``X-CSRF-Token`` equal to the ``me_csrf``
cookie. Another site can make the browser send our cookies, but it cannot read
``me_csrf`` and so cannot set the header. One ``before_request`` hook protects
every current and future route.

Exempt: sign-in, which accepts only JSON (cross-site forms cannot send it) and
must work even when stale cookies are present. Requests with no session cookie
carry no ambient authority, so there is nothing to forge.
"""

from __future__ import annotations

import hmac

from flask import Flask, request

from mediease_api.delivery.http.session_cookies import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    REFRESH_COOKIE,
)
from mediease_api.domain.shared.errors import DomainError

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT_PATHS = frozenset({"/api/v1/auth/sign-in"})


class CsrfInvalid(DomainError):
    code = "AUTH_CSRF_INVALID"

    def __init__(self) -> None:
        super().__init__("This request could not be verified. Reload the page and try again.")


def register_csrf_protection(app: Flask) -> None:
    @app.before_request
    def _require_csrf_token() -> None:
        if request.method in _SAFE_METHODS or not request.path.startswith("/api/"):
            return
        if request.path in _EXEMPT_PATHS:
            return
        if ACCESS_COOKIE not in request.cookies and REFRESH_COOKIE not in request.cookies:
            return
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get(CSRF_HEADER, "")
        if not cookie or not hmac.compare_digest(cookie.encode(), header.encode()):
            raise CsrfInvalid()
