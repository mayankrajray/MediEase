"""Auth endpoints: sign-in, refresh, sign-out (FR-AUTH-01, 02, 04; spec R1-R5).

Responses carry the user, their clinics and the session's expiry times —
never a token (R4). Tokens travel only in cookies. Every response is
``Cache-Control: no-store``.

Use cases are built per request by the composition root (``AuthUseCases``),
so each request gets its own unit of work.
"""

from __future__ import annotations

from typing import Any, Protocol

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.auth.errors import (
    AccountDisabled,
    RefreshTokenReused,
    SessionExpired,
)
from mediease_api.application.auth.refresh_session import RefreshSession
from mediease_api.application.auth.sign_in import SignIn, SignInCommand
from mediease_api.application.auth.sign_out import SignOut
from mediease_api.application.auth.views import SessionResult
from mediease_api.delivery.errors import domain_error_response
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.me import identity_body
from mediease_api.delivery.http.session_cookies import (
    REFRESH_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from mediease_api.delivery.http.validation import parse_json


class AuthUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def sign_in(self) -> SignIn: ...
    def refresh(self) -> RefreshSession: ...
    def sign_out(self) -> SignOut: ...


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    # Email or phone number; normalised by the use case (R1).
    identifier: str = Field(min_length=1, max_length=254)
    # Upper bound keeps a hostile body from costing an unbounded hash.
    password: str = Field(min_length=1, max_length=1024)


def create_auth_blueprint(use_cases: AuthUseCases, *, cookie_secure: bool) -> Blueprint:
    bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/sign-in")
    @public
    def sign_in() -> Response:
        body = parse_json(SignInRequest)
        result = use_cases.sign_in().execute(
            SignInCommand(identifier=body.identifier, password=body.password)
        )
        return _session_response(result, cookie_secure)

    @bp.post("/refresh")
    @public
    def refresh() -> Response | tuple[Response, int]:
        token = request.cookies.get(REFRESH_COOKIE)
        try:
            if not token:
                raise SessionExpired()
            result = use_cases.refresh().execute(token)
        except (SessionExpired, RefreshTokenReused, AccountDisabled) as exc:
            # The session is over: tell the browser to drop the cookies too.
            response, status = domain_error_response(exc)
            clear_session_cookies(response, secure=cookie_secure)
            return response, status
        return _session_response(result, cookie_secure)

    @bp.post("/sign-out")
    @public
    def sign_out() -> Response:
        use_cases.sign_out().execute(request.cookies.get(REFRESH_COOKIE))
        response = Response(status=204)
        clear_session_cookies(response, secure=cookie_secure)
        return response

    return bp


def _session_response(result: SessionResult, cookie_secure: bool) -> Response:
    response = jsonify(_session_body(result))
    set_session_cookies(response, result.tokens, secure=cookie_secure)
    return response


def _session_body(result: SessionResult) -> dict[str, Any]:
    return {
        **identity_body(result.user, result.memberships),
        "session": {
            "access_expires_at": result.tokens.access_expires_at.isoformat(),
            "refresh_expires_at": result.tokens.refresh_expires_at.isoformat(),
        },
    }
