"""Authorisation end to end against real PostgreSQL (FR-AUTH-03, FR-ORG-04; R6-R10, AC4).

Drives the whole stack: cookies, the access hook, per-request re-checks and
the clinic endpoints. Cross-clinic isolation (AC3) is proved in
``tests/tenancy/test_http_isolation.py``.
"""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mediease_api.delivery.http.access import ops
from mediease_api.domain.identity.membership import Role
from tests.conftest import UowFactory, World

ME = "/api/v1/me"
CLINIC = "/api/v1/clinic"
DOCTORS = "/api/v1/clinic/doctors"
STAFF = "/api/v1/clinic/staff"
CLINIC_ROUTES = (CLINIC, DOCTORS, STAFF)


def _error(resp: TestResponse) -> dict[str, object]:
    return dict(resp.get_json()["error"])


# --- The role matrix (PRD §8.1) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "path", "status"),
    [
        (Role.OWNER, CLINIC, 200),
        (Role.OWNER, DOCTORS, 200),
        (Role.OWNER, STAFF, 200),
        (Role.DOCTOR, CLINIC, 200),
        (Role.DOCTOR, DOCTORS, 200),
        (Role.DOCTOR, STAFF, 403),
        (Role.FRONT_DESK, CLINIC, 200),
        (Role.FRONT_DESK, DOCTORS, 200),
        (Role.FRONT_DESK, STAFF, 403),
    ],
)
def test_fr_auth_03_permission_matrix_on_every_clinic_route(
    world: World, role: Role, path: str, status: int
) -> None:
    resp = world.client_for(world.a.user_for(role)).get(path)
    assert resp.status_code == status
    if status == 403:
        error = _error(resp)
        assert error["code"] == "PERM_DENIED"
        assert error["details"] == {"permission": "STAFF_MANAGE", "role": role.value}


@pytest.mark.parametrize("role", list(Role))
def test_fr_auth_03_every_role_can_read_their_own_identity(world: World, role: Role) -> None:
    resp = world.client_for(world.a.user_for(role)).get(ME)
    assert resp.status_code == 200
    body = resp.get_json()
    assert resp.headers["Cache-Control"] == "no-store"
    assert body["user"]["id"] == str(world.a.user_for(role).id)
    membership = body["memberships"][0]
    assert membership["clinic_id"] == str(world.a.clinic.id)
    assert membership["clinic_status"] == "ACTIVE"
    assert membership["role"] == role.value
    assert ("STAFF_MANAGE" in membership["permissions"]) is (role is Role.OWNER)
    assert ("CLINICAL_WRITE" in membership["permissions"]) is (role is Role.DOCTOR)


def test_clinic_endpoint_returns_the_requests_clinic(world: World) -> None:
    resp = world.client_for(world.a.desk).get(CLINIC)
    body = resp.get_json()
    assert body["id"] == str(world.a.clinic.id)
    assert body["name"] == "Alpha Sample Clinic"
    assert body["status"] == "ACTIVE"
    assert body["timezone"] == "Asia/Kolkata"
    assert resp.headers["Cache-Control"] == "no-store"


def test_doctors_and_staff_lists_describe_this_clinic(world: World) -> None:
    client = world.client_for(world.a.owner)
    doctors = client.get(DOCTORS).get_json()["items"]
    assert [d["id"] for d in doctors] == [str(world.a.doctor.id)]
    assert doctors[0]["registration_number"] == world.a.doctor.registration_number

    staff = client.get(STAFF).get_json()["items"]
    assert [(s["full_name"], s["role"], s["status"]) for s in staff] == [
        ("Alpha Doctor", "DOCTOR", "ACTIVE"),
        ("Alpha Front_Desk", "FRONT_DESK", "ACTIVE"),
        ("Alpha Owner", "OWNER", "ACTIVE"),
        ("Multi Clinic", "FRONT_DESK", "ACTIVE"),
    ]


def test_one_doctor_of_this_clinic_is_readable_by_id(world: World) -> None:
    resp = world.client_for(world.a.doctor_user).get(f"{DOCTORS}/{world.a.doctor.id}")
    assert resp.status_code == 200
    assert resp.get_json()["display_name"] == "Dr. Alpha Sample"


def test_unknown_doctor_id_is_404(world: World) -> None:
    resp = world.client_for(world.a.owner).get(f"{DOCTORS}/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "REQ_NOT_FOUND"


# --- No session, no access -------------------------------------------------------------------


@pytest.mark.parametrize("path", [ME, *CLINIC_ROUTES])
def test_fr_auth_03_signed_out_requests_are_401(world: World, path: str) -> None:
    resp = world.anonymous().get(path)
    assert resp.status_code == 401
    assert _error(resp)["code"] == "AUTH_SESSION_EXPIRED"


@pytest.mark.parametrize("path", ["/health", "/ready"])
def test_public_routes_need_no_session(world: World, path: str) -> None:
    assert world.anonymous().get(path).status_code == 200


def test_a_tampered_access_cookie_is_401(world: World) -> None:
    client = world.client_for(world.a.owner)
    client.set_cookie("me_access", "not.a.jwt", path="/api")
    assert client.get(ME).status_code == 401


def test_fr_auth_02_signing_out_ends_access_at_once(world: World) -> None:
    client = world.client_for(world.a.owner)
    access = client.get_cookie("me_access", path="/api")
    assert access is not None
    assert client.get(ME).status_code == 200

    assert client.post("/api/v1/auth/sign-out", headers=_csrf(client)).status_code == 204
    # Someone who kept the access token gains nothing: its session is gone, so
    # access ends now instead of when the 15-minute token expires.
    client.set_cookie("me_access", access.value, path="/api")
    resp = client.get(ME)
    assert resp.status_code == 401
    assert _error(resp)["code"] == "AUTH_SESSION_EXPIRED"


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


# --- R7: deactivation takes effect on the next request (AC4) --------------------------------


def test_ac4_fr_org_04_deactivated_member_is_refused_on_the_next_request(
    world: World, uow_factory: UowFactory
) -> None:
    client = world.client_for(world.a.desk)
    assert client.get(CLINIC).status_code == 200

    with uow_factory() as uow:
        memberships = uow.tenant(world.a.clinic.id).memberships
        membership = memberships.get_for_user(world.a.desk.id)
        assert membership is not None
        membership.deactivate(active_owner_count=1, now=membership.updated_at)
        memberships.update(membership)
        uow.commit()

    resp = client.get(CLINIC)  # same cookies, same access token
    assert resp.status_code == 403
    assert _error(resp)["code"] == "AUTH_ACCOUNT_DISABLED"
    assert client.get(ME).status_code == 403


def test_r7_disabled_user_is_refused_on_the_next_request(
    world: World, uow_factory: UowFactory
) -> None:
    client = world.client_for(world.a.doctor_user)
    with uow_factory() as uow:
        user = uow.users.get(world.a.doctor_user.id)
        assert user is not None
        user.disable(now=user.updated_at)
        uow.users.update(user)
        uow.commit()

    resp = client.get(DOCTORS)
    assert resp.status_code == 403
    assert _error(resp)["code"] == "AUTH_ACCOUNT_DISABLED"


# --- R6: which clinic is this request for? ---------------------------------------------------


def test_r6_multi_clinic_user_must_choose_a_clinic(world: World) -> None:
    resp = world.client_for(world.multi).get(CLINIC)
    assert resp.status_code == 400
    error = _error(resp)
    assert error["code"] == "PERM_CLINIC_REQUIRED"
    assert error["details"] == {}


def test_r6_x_clinic_id_selects_the_membership_and_its_role(world: World) -> None:
    client = world.client_for(world.multi)
    in_a = client.get(CLINIC, headers={"X-Clinic-ID": str(world.a.clinic.id)})
    assert in_a.get_json()["name"] == "Alpha Sample Clinic"
    in_b = client.get(CLINIC, headers={"X-Clinic-ID": str(world.b.clinic.id)})
    assert in_b.get_json()["name"] == "Beta Sample Clinic"

    # FRONT_DESK in A, OWNER in B: the same user, different permissions.
    assert client.get(STAFF, headers={"X-Clinic-ID": str(world.a.clinic.id)}).status_code == 403
    assert client.get(STAFF, headers={"X-Clinic-ID": str(world.b.clinic.id)}).status_code == 200


def test_r6_a_header_the_user_has_no_membership_for_looks_like_a_missing_choice(
    world: World,
) -> None:
    """Same 400 as "choose a clinic": the answer never says whether the clinic exists."""
    client = world.client_for(world.a.owner)
    for header in (
        str(world.b.clinic.id),  # exists, but not theirs
        "00000000-0000-0000-0000-000000000009",  # does not exist
        "not-a-uuid",
    ):
        resp = client.get(CLINIC, headers={"X-Clinic-ID": header})
        assert resp.status_code == 400
        assert _error(resp)["code"] == "PERM_CLINIC_REQUIRED"


def test_a_suspended_clinic_is_refused_with_its_own_code(world: World) -> None:
    resp = world.client_for(world.suspended_owner).get(CLINIC)
    assert resp.status_code == 403
    assert _error(resp)["code"] == "CLN_SUSPENDED"
    # /me still shows it, with its status, so the web app can explain why.
    me = world.client_for(world.suspended_owner).get(ME).get_json()
    assert me["memberships"][0]["clinic_status"] == "SUSPENDED"


# --- R10: ops users ---------------------------------------------------------------------------


def test_r10_ops_user_is_authenticated_but_refused_on_clinic_routes(world: World) -> None:
    client = world.client_for(world.ops)
    me = client.get(ME)
    assert me.status_code == 200
    assert me.get_json()["user"]["is_platform_ops"] is True
    assert me.get_json()["memberships"] == []

    for path in CLINIC_ROUTES:
        resp = client.get(path)
        assert resp.status_code == 403, path
        assert _error(resp)["code"] == "PERM_DENIED"


def test_r10_an_ops_route_refuses_clinic_staff(world: World) -> None:
    """The first real ops endpoints arrive in M1-P5; the policy they will use is proved here."""

    @world.app.get("/api/v1/ops/ping")
    @ops
    def _ops_ping() -> dict[str, str]:
        return {"status": "ok"}

    assert world.client_for(world.ops).get("/api/v1/ops/ping").status_code == 200

    refused = world.client_for(world.a.owner).get("/api/v1/ops/ping")
    assert refused.status_code == 403
    assert _error(refused)["code"] == "PERM_DENIED"
    assert world.anonymous().get("/api/v1/ops/ping").status_code == 401
