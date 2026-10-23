"""Patient portal accounts: sign-up, sign-in, refresh, sign-out and ``/me`` (M6a-P3, ADR-0015).

Under ``/api/v1/portal``, apart from staff auth: the portal cookies (``me_pt_*``), the
``mediease-portal`` audience and the ``@patient`` policy. Bodies carry the account and the
session's expiry times, never a token. Every response is ``Cache-Control: no-store``.

The account holds no clinic data yet; linking it to a clinic's patient record is M6b.
"""

from __future__ import annotations

from typing import Any, Protocol

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.auth.errors import RefreshTokenReused, SessionExpired
from mediease_api.application.portal.errors import PortalAccountDisabled
from mediease_api.application.portal.use_cases import (
    PortalSignInCommand,
    RefreshPatientSession,
    SignInPatient,
    SignOutPatient,
    SignUpCommand,
    SignUpPatient,
    account_view,
)
from mediease_api.application.portal.views import PatientAccountView, PatientSessionResult
from mediease_api.delivery.errors import domain_error_response
from mediease_api.delivery.http.access import current_patient, patient, public
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.session_cookies import (
    PORTAL_COOKIES,
    PORTAL_REFRESH_COOKIE,
    clear_session_cookies,
    set_session_cookies,
)
from mediease_api.delivery.http.validation import parse_json


class PortalUseCases(Protocol):
    def sign_up_patient(self) -> SignUpPatient: ...
    def sign_in_patient(self) -> SignInPatient: ...
    def refresh_patient(self) -> RefreshPatientSession: ...
    def sign_out_patient(self) -> SignOutPatient: ...


class SignUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=254)
    # The policy (12 characters minimum) is the domain's; the cap bounds the hashing cost.
    password: str = Field(min_length=1, max_length=1024)


class PortalSignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


def account_body(account: PatientAccountView) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "full_name": account.full_name,
        "email": account.email,
        "sign_in_method": account.sign_in_method.value,
        "email_verified": account.email_verified,
    }


def portal_session_response(
    result: PatientSessionResult, cookie_secure: bool, status: int = 200
) -> Response:
    """The account plus the portal cookies. Shared with Google sign-in for patients."""
    response = jsonify(
        {
            "account": account_body(result.account),
            "session": {
                "access_expires_at": result.tokens.access_expires_at.isoformat(),
                "refresh_expires_at": result.tokens.refresh_expires_at.isoformat(),
            },
        }
    )
    response.status_code = status
    set_session_cookies(response, result.tokens, secure=cookie_secure, cookies=PORTAL_COOKIES)
    response.headers["Cache-Control"] = "no-store"
    return response


def create_portal_blueprint(use_cases: PortalUseCases, *, cookie_secure: bool) -> Blueprint:
    bp = Blueprint("portal", __name__, url_prefix="/api/v1/portal")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/auth/sign-up")
    @public
    def sign_up() -> Response:
        body = parse_json(SignUpRequest)
        result = use_cases.sign_up_patient().execute(
            SignUpCommand(full_name=body.full_name, email=body.email, password=body.password),
            request_info(),
        )
        return portal_session_response(result, cookie_secure, status=201)

    @bp.post("/auth/sign-in")
    @public
    def sign_in() -> Response:
        body = parse_json(PortalSignInRequest)
        result = use_cases.sign_in_patient().execute(
            PortalSignInCommand(email=body.email, password=body.password), request_info()
        )
        return portal_session_response(result, cookie_secure)

    @bp.post("/auth/refresh")
    @public
    def refresh() -> Response | tuple[Response, int]:
        token = request.cookies.get(PORTAL_REFRESH_COOKIE)
        try:
            if not token:
                raise SessionExpired()
            result = use_cases.refresh_patient().execute(token, request_info())
        except (SessionExpired, RefreshTokenReused, PortalAccountDisabled) as exc:
            response, status = domain_error_response(exc)
            clear_session_cookies(response, secure=cookie_secure, cookies=PORTAL_COOKIES)
            return response, status
        return portal_session_response(result, cookie_secure)

    @bp.post("/auth/sign-out")
    @public
    def sign_out() -> Response:
        use_cases.sign_out_patient().execute(
            request.cookies.get(PORTAL_REFRESH_COOKIE), request_info()
        )
        response = Response(status=204)
        clear_session_cookies(response, secure=cookie_secure, cookies=PORTAL_COOKIES)
        return response

    @bp.get("/me")
    @patient
    def me() -> Response:
        return jsonify({"account": account_body(account_view(current_patient()))})

    return bp
