"""Default deny: every route declares an access policy (FR-AUTH-03, spec R6-R10).

These are the structural guards. Who may actually call what is proved end to
end in ``tests/integration/test_authorization_http.py``.
"""

from __future__ import annotations

import pytest
from flask import Flask

from mediease_api.delivery.http.access import (
    Access,
    MissingAccessPolicy,
    check_every_route_has_policy,
    current_context,
    current_principal,
    policy_of,
)
from mediease_api.domain.identity.permissions import Permission

# The whole HTTP surface after M1-P5, and the policy each route carries.
EXPECTED_POLICIES = {
    "platform.health": (Access.PUBLIC, None),
    "platform.ready": (Access.PUBLIC, None),
    "auth.sign_in": (Access.PUBLIC, None),
    "auth.refresh": (Access.PUBLIC, None),
    "auth.sign_out": (Access.PUBLIC, None),
    # The authority is the invitation secret in the URL, not a session.
    "invites.describe_invite": (Access.PUBLIC, None),
    "invites.accept_invite": (Access.PUBLIC, None),
    "me.me": (Access.AUTHENTICATED, None),
    "clinic.get_clinic": (Access.CLINIC, Permission.CLINIC_VIEW),
    "clinic.update_clinic": (Access.CLINIC, Permission.CLINIC_MANAGE),
    "clinic.list_doctors": (Access.CLINIC, Permission.DOCTORS_VIEW),
    "clinic.add_doctor": (Access.CLINIC, Permission.CLINIC_MANAGE),
    "clinic.get_doctor": (Access.CLINIC, Permission.DOCTORS_VIEW),
    "clinic.update_doctor": (Access.CLINIC, Permission.CLINIC_MANAGE),
    "clinic.list_staff": (Access.CLINIC, Permission.STAFF_MANAGE),
    "clinic.invite_staff": (Access.CLINIC, Permission.STAFF_MANAGE),
    "clinic.change_membership": (Access.CLINIC, Permission.STAFF_MANAGE),
    "ops.create_clinic": (Access.OPS, None),
    "ops.list_clinics": (Access.OPS, None),
    "ops.get_clinic": (Access.OPS, None),
    "ops.add_doctor": (Access.OPS, None),
    "ops.invite_staff": (Access.OPS, None),
}


def test_fr_auth_03_every_route_declares_the_expected_policy(app: Flask) -> None:
    """A new endpoint must appear here — and in the authorisation tests — on purpose."""
    actual = {}
    for endpoint, view in app.view_functions.items():
        policy = policy_of(view)
        assert policy is not None, endpoint
        actual[endpoint] = (policy.access, policy.permission)
    assert actual == EXPECTED_POLICIES


def test_fr_auth_03_an_app_with_an_undeclared_route_does_not_start(app: Flask) -> None:
    @app.get("/forgotten")
    def _forgotten() -> str:
        return "no policy"

    with pytest.raises(MissingAccessPolicy, match="_forgotten"):
        check_every_route_has_policy(app)


def test_fr_auth_03_calling_an_undeclared_route_is_refused_not_served(app: Flask) -> None:
    """Belt and braces: a route registered after start-up is never served either."""

    @app.get("/forgotten")
    def _forgotten() -> str:
        return "no policy"

    resp = app.test_client().get("/forgotten")
    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "SYS_UNEXPECTED"
    assert "no policy" not in resp.get_data(as_text=True)


def test_context_accessors_fail_loudly_on_the_wrong_policy(app: Flask) -> None:
    @app.get("/public-route")
    def _public_route() -> str:
        return "ok"

    with app.test_request_context("/public-route"):
        with pytest.raises(RuntimeError, match="@authenticated"):
            current_principal()
        with pytest.raises(RuntimeError, match="@clinic"):
            current_context()
