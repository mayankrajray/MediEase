"""Session cookies (ADR-0006, spec R4).

| Cookie       | Holds                  | Path            | HttpOnly | Lifetime          |
|--------------|------------------------|-----------------|----------|-------------------|
| ``me_access``  | access JWT             | ``/api``          | yes      | access token      |
| ``me_refresh`` | refresh token          | ``/api/v1/auth``  | yes      | refresh token     |
| ``me_csrf``    | CSRF double-submit key | ``/``             | no       | refresh token     |

All are ``SameSite=Lax`` and ``Secure`` when ``COOKIE_SECURE`` is true (it
must be outside local http). The refresh token is only ever sent to the auth
endpoints. ``me_csrf`` is readable by the web app's scripts on purpose: they
copy it into ``X-CSRF-Token`` (``delivery/http/csrf.py``).
"""

from __future__ import annotations

import secrets

from flask import Response

from mediease_api.application.auth.views import SessionTokens

ACCESS_COOKIE = "me_access"
REFRESH_COOKIE = "me_refresh"
CSRF_COOKIE = "me_csrf"
CSRF_HEADER = "X-CSRF-Token"

_PATHS = {ACCESS_COOKIE: "/api", REFRESH_COOKIE: "/api/v1/auth", CSRF_COOKIE: "/"}


def set_session_cookies(response: Response, tokens: SessionTokens, *, secure: bool) -> None:
    csrf_token = secrets.token_urlsafe(32)
    values = {
        ACCESS_COOKIE: (tokens.access_token, tokens.access_expires_at, True),
        REFRESH_COOKIE: (tokens.refresh_token, tokens.refresh_expires_at, True),
        CSRF_COOKIE: (csrf_token, tokens.refresh_expires_at, False),
    }
    for name, (value, expires, http_only) in values.items():
        response.set_cookie(
            name,
            value,
            expires=expires,
            path=_PATHS[name],
            secure=secure,
            httponly=http_only,
            samesite="Lax",
        )


def clear_session_cookies(response: Response, *, secure: bool) -> None:
    for name, path in _PATHS.items():
        response.delete_cookie(
            name, path=path, secure=secure, httponly=name != CSRF_COOKIE, samesite="Lax"
        )
