"""CSRF protection by double submit (ADR-0006, ARCHITECTURE.md §9; portal ADR-0015).

Every unsafe request (anything but GET/HEAD/OPTIONS) under ``/api/`` that carries a session
cookie must send ``X-CSRF-Token`` equal to that session's CSRF cookie. Another site can make the
browser send our cookies, but it cannot read the CSRF cookie and so cannot set the header. One
``before_request`` hook protects every current and future route.

Two sessions, two cookie sets (M6a-P3): requests under ``/api/v1/portal/`` are checked against
the portal set (``me_pt_access``/``me_pt_refresh`` and ``me_pt_csrf``), everything else against
the staff set. The browser also sends the staff ``me_access`` (path ``/api``) to portal paths,
but portal routes never read it, so it carries no authority there.

Exempt: sign-in (staff and portal) and portal sign-up, which accept only JSON (cross-site forms
cannot send it) and must work even when stale cookies are present, and accepting a staff
invitation, whose authority is the secret in the URL rather than the cookie (M1-P5). Requests
with no session cookie carry no ambient authority, so there is nothing to forge.
"""

from __future__ import annotations

import hmac

from flask import Flask, request

from mediease_api.delivery.http.session_cookies import (
    CSRF_HEADER,
    PORTAL_COOKIES,
    STAFF_COOKIES,
)
from mediease_api.domain.shared.errors import DomainError

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/auth/sign-in",
        "/api/v1/portal/auth/sign-in",
        "/api/v1/portal/auth/sign-up",
        # M6a-P4: anonymous by nature; the authority is the address or the emailed token.
        "/api/v1/auth/password-reset",
        "/api/v1/auth/password-reset/complete",
        "/api/v1/portal/auth/password-reset",
        "/api/v1/portal/auth/password-reset/complete",
        "/api/v1/portal/auth/verify-email",
    }
)
# The token is in the path, so the exemption is by prefix.
_EXEMPT_PREFIXES = ("/api/v1/auth/invites/",)
_PORTAL_PREFIX = "/api/v1/portal/"


class CsrfInvalid(DomainError):
    code = "AUTH_CSRF_INVALID"

    def __init__(self) -> None:
        super().__init__("This request could not be verified. Reload the page and try again.")


def register_csrf_protection(app: Flask) -> None:
    @app.before_request
    def _require_csrf_token() -> None:
        if request.method in _SAFE_METHODS or not request.path.startswith("/api/"):
            return
        if request.path in _EXEMPT_PATHS or request.path.startswith(_EXEMPT_PREFIXES):
            return
        cookies = PORTAL_COOKIES if request.path.startswith(_PORTAL_PREFIX) else STAFF_COOKIES
        if cookies.access not in request.cookies and cookies.refresh not in request.cookies:
            return
        cookie = request.cookies.get(cookies.csrf, "")
        header = request.headers.get(CSRF_HEADER, "")
        if not cookie or not hmac.compare_digest(cookie.encode(), header.encode()):
            raise CsrfInvalid()
