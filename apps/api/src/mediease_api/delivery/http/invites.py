"""Accepting a staff invitation — the only public write in M1 (FR-ORG-04).

| Endpoint | Purpose |
|---|---|
| ``GET /api/v1/auth/invites/{token}`` | What this link is for, before signing anything |
| ``POST /api/v1/auth/invites/{token}/accept`` | Set a password, activate, sign in |

No session is involved: the authority is the secret in the URL. That is also
why these paths are exempt from the CSRF header (``delivery/http/csrf.py``) —
a cross-site request would need the secret, and a signed-in user clicking an
invitation link must not be refused.

Accepting returns the same session body as sign-in and sets the same cookies,
so the invitee lands in the app already signed in.
"""

from __future__ import annotations

from typing import Any, Protocol

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.identity.accept_invite import (
    AcceptInvite,
    DescribeInvite,
    InviteView,
)
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.auth import session_response
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json

# Keep the URL token bounded: the secret is 43 characters of URL-safe base64.
MAX_TOKEN_LENGTH = 128


class InviteUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def describe_invite(self) -> DescribeInvite: ...
    def accept_invite(self) -> AcceptInvite: ...


class AcceptInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The domain enforces the policy (12 characters); this is the outer bound.
    password: str = Field(min_length=1, max_length=1024)


def create_invite_blueprint(use_cases: InviteUseCases, *, cookie_secure: bool) -> Blueprint:
    bp = Blueprint("invites", __name__, url_prefix="/api/v1/auth/invites")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("/<string(maxlength=128):token>")
    @public
    def describe_invite(token: str) -> Response:
        return jsonify(_invite_body(use_cases.describe_invite().execute(token)))

    @bp.post("/<string(maxlength=128):token>/accept")
    @public
    def accept_invite(token: str) -> Response:
        body = parse_json(AcceptInviteRequest)
        result = use_cases.accept_invite().execute(token, body.password, request_info())
        return session_response(result, cookie_secure)

    return bp


def _invite_body(view: InviteView) -> dict[str, Any]:
    return {
        "clinic_name": view.clinic_name,
        "full_name": view.full_name,
        "role": view.role.value,
        "expires_at": view.expires_at.isoformat() if view.expires_at else None,
        # The web page can say "sign in instead" rather than asking for a new password.
        "has_password": view.has_password,
    }
