"""Session cookies (ADR-0006, spec R4; portal cookies ADR-0015 decision 2).

Staff:

| Cookie       | Holds                  | Path            | HttpOnly | Lifetime          |
|--------------|------------------------|-----------------|----------|-------------------|
| ``me_access``  | access JWT             | ``/api``          | yes      | access token      |
| ``me_refresh`` | refresh token          | ``/api/v1/auth``  | yes      | refresh token     |
| ``me_csrf``    | CSRF double-submit key | ``/``             | no       | refresh token     |

Patient portal (M6a-P3), a separate set so the two sessions never share a cookie:

| Cookie          | Holds                  | Path                    | HttpOnly |
|-----------------|------------------------|-------------------------|----------|
| ``me_pt_access``  | portal access JWT      | ``/api/v1/portal``        | yes      |
| ``me_pt_refresh`` | portal refresh token   | ``/api/v1/portal/auth``   | yes      |
| ``me_pt_csrf``    | CSRF double-submit key | ``/``                     | no       |

All are ``SameSite=Lax`` and ``Secure`` when ``COOKIE_SECURE`` is true (it must be outside local
http). A refresh token is only ever sent to its own auth endpoints. The CSRF cookies are readable
by the web app's scripts on purpose: they copy them into ``X-CSRF-Token``
(``delivery/http/csrf.py``).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from flask import Response

from mediease_api.application.auth.views import SessionTokens

CSRF_HEADER = "X-CSRF-Token"


@dataclass(frozen=True, slots=True)
class CookieSet:
    access: str
    refresh: str
    csrf: str
    access_path: str
    refresh_path: str

    def paths(self) -> dict[str, str]:
        return {self.access: self.access_path, self.refresh: self.refresh_path, self.csrf: "/"}


STAFF_COOKIES = CookieSet("me_access", "me_refresh", "me_csrf", "/api", "/api/v1/auth")
PORTAL_COOKIES = CookieSet(
    "me_pt_access", "me_pt_refresh", "me_pt_csrf", "/api/v1/portal", "/api/v1/portal/auth"
)

ACCESS_COOKIE = STAFF_COOKIES.access
REFRESH_COOKIE = STAFF_COOKIES.refresh
CSRF_COOKIE = STAFF_COOKIES.csrf
PORTAL_ACCESS_COOKIE = PORTAL_COOKIES.access
PORTAL_REFRESH_COOKIE = PORTAL_COOKIES.refresh
PORTAL_CSRF_COOKIE = PORTAL_COOKIES.csrf


def set_session_cookies(
    response: Response, tokens: SessionTokens, *, secure: bool, cookies: CookieSet = STAFF_COOKIES
) -> None:
    csrf_token = secrets.token_urlsafe(32)
    values = {
        cookies.access: (tokens.access_token, tokens.access_expires_at, True),
        cookies.refresh: (tokens.refresh_token, tokens.refresh_expires_at, True),
        cookies.csrf: (csrf_token, tokens.refresh_expires_at, False),
    }
    paths = cookies.paths()
    for name, (value, expires, http_only) in values.items():
        response.set_cookie(
            name,
            value,
            expires=expires,
            path=paths[name],
            secure=secure,
            httponly=http_only,
            samesite="Lax",
        )


def clear_session_cookies(
    response: Response, *, secure: bool, cookies: CookieSet = STAFF_COOKIES
) -> None:
    for name, path in cookies.paths().items():
        response.delete_cookie(
            name, path=path, secure=secure, httponly=name != cookies.csrf, samesite="Lax"
        )
