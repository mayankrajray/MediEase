"""``GET /api/v1/me`` — the signed-in user, their clinics and their permissions (FR-AUTH-03).

The web app calls this on load and after every refresh to decide what to show
(clinic switcher, which menu items a role gets). Authorising the request has
already re-read the user and the memberships, so there is no extra query.

The body builders here are shared with the sign-in and refresh responses
(``delivery/http/auth.py``), so one user shape is sent everywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from flask import Blueprint, Response, jsonify

from mediease_api.application.auth.views import MembershipView, UserView
from mediease_api.application.identity.me import me_view
from mediease_api.delivery.http.access import authenticated, current_principal


def user_body(user: UserView) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "full_name": user.full_name,
        "email": user.email,
        "phone_e164": user.phone_e164,
        "is_platform_ops": user.is_platform_ops,
    }


def membership_body(membership: MembershipView) -> dict[str, Any]:
    return {
        "membership_id": str(membership.membership_id),
        "clinic_id": str(membership.clinic_id),
        "clinic_name": membership.clinic_name,
        "clinic_status": membership.clinic_status.value,
        "role": membership.role.value,
        "permissions": [p.value for p in membership.permissions],
    }


def identity_body(user: UserView, memberships: Sequence[MembershipView]) -> dict[str, Any]:
    """The ``{user, memberships}`` pair returned by ``/me``, sign-in and refresh."""
    return {
        "user": user_body(user),
        "memberships": [membership_body(m) for m in memberships],
    }


def create_me_blueprint() -> Blueprint:
    bp = Blueprint("me", __name__, url_prefix="/api/v1")

    @bp.get("/me")
    @authenticated
    def me() -> Response:
        view = me_view(current_principal())
        response = jsonify(identity_body(view.user, view.memberships))
        # Permissions and membership status must never be served from a cache.
        response.headers["Cache-Control"] = "no-store"
        return response

    return bp
