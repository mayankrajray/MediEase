"""The audit log end to end against real PostgreSQL (FR-AUD-01; spec R11, AC5).

Drives the whole stack — cookies, the access hook, the use case, the
append-only table — and reads the rows back with SQL, the way an owner or an
investigation would.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.test import TestResponse

from mediease_api.domain.identity.membership import Role
from tests.conftest import World

STAFF = "/api/v1/clinic/staff"
SessionFactory = sessionmaker[Session]


def _events(session_factory: SessionFactory, action: str | None = None) -> list[dict[str, Any]]:
    where = "WHERE action = :action" if action else ""
    with session_factory() as session:
        rows = session.execute(
            text(f"SELECT * FROM audit_events {where} ORDER BY occurred_at, id"),
            {"action": action} if action else {},
        )
        return [dict(row) for row in rows.mappings()]


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def _patch_role(
    client: FlaskClient, membership_id: UUID, role: Role, *, request_id: str | None = None
) -> TestResponse:
    headers = _csrf(client)
    if request_id:
        headers["X-Request-ID"] = request_id
    return client.patch(f"{STAFF}/{membership_id}", json={"role": role.value}, headers=headers)


def _membership_id(client: FlaskClient, full_name: str) -> UUID:
    staff = client.get(STAFF).get_json()["items"]
    return UUID(next(m["membership_id"] for m in staff if m["full_name"] == full_name))


# --- AC5: a role change is recorded exactly once --------------------------------------------


def test_ac5_fr_aud_01_a_role_change_writes_one_event_with_actor_and_target(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _membership_id(owner, "Alpha Front_Desk")

    resp = _patch_role(owner, membership_id, Role.DOCTOR, request_id="role-change-1")
    assert resp.status_code == 200
    assert resp.get_json()["role"] == "DOCTOR"
    assert resp.get_json()["full_name"] == "Alpha Front_Desk"

    events = _events(session_factory, "staff.role_changed")
    assert len(events) == 1
    event = events[0]
    assert event["actor_user_id"] == world.a.owner.id
    assert event["actor_type"] == "STAFF"
    assert event["clinic_id"] == world.a.clinic.id
    assert (event["entity_type"], event["entity_id"]) == ("clinic_membership", membership_id)
    assert event["request_id"] == "role-change-1"
    assert event["metadata"] == {
        "target_user_id": str(world.a.desk.id),
        "from_role": "FRONT_DESK",
        "to_role": "DOCTOR",
    }
    # The IP is a fingerprint, not an address.
    assert event["ip_hash"] and "127.0.0.1" not in event["ip_hash"]


def test_fr_org_04_the_new_role_applies_to_the_members_next_request(world: World) -> None:
    owner = world.client_for(world.a.owner)
    doctor = world.client_for(world.a.doctor_user)
    assert "CLINICAL_WRITE" in doctor.get("/api/v1/me").get_json()["memberships"][0]["permissions"]

    _patch_role(owner, _membership_id(owner, "Alpha Doctor"), Role.FRONT_DESK)

    # Same session, same cookies: M1-P3 re-reads the membership every request.
    membership = doctor.get("/api/v1/me").get_json()["memberships"][0]
    assert membership["role"] == "FRONT_DESK"
    assert "CLINICAL_WRITE" not in membership["permissions"]


def test_r9_demoting_the_last_owner_is_refused_and_records_nothing(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)
    resp = _patch_role(owner, _membership_id(owner, "Alpha Owner"), Role.DOCTOR)

    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CLN_LAST_OWNER"
    assert _events(session_factory, "staff.role_changed") == []


def test_setting_the_same_role_changes_nothing_and_records_nothing(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _membership_id(owner, "Alpha Doctor")
    resp = _patch_role(owner, membership_id, Role.DOCTOR)

    assert resp.status_code == 200
    assert resp.get_json()["role"] == "DOCTOR"
    assert _events(session_factory, "staff.role_changed") == []


def test_fr_auth_03_a_doctor_cannot_change_roles_and_records_nothing(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _membership_id(owner, "Alpha Front_Desk")

    refused = _patch_role(world.client_for(world.a.doctor_user), membership_id, Role.DOCTOR)
    assert refused.status_code == 403
    assert refused.get_json()["error"]["code"] == "PERM_DENIED"
    assert _events(session_factory, "staff.role_changed") == []


def test_the_role_change_needs_the_csrf_header(world: World) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _membership_id(owner, "Alpha Front_Desk")

    resp = owner.patch(f"{STAFF}/{membership_id}", json={"role": "DOCTOR"})
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "AUTH_CSRF_INVALID"


@pytest.mark.parametrize(
    "body",
    [{"role": "SUPERUSER"}, {}, {"role": "OWNER", "status": "ACTIVE"}],
    ids=["unknown-role", "missing-role", "extra-field"],
)
def test_an_invalid_role_change_body_is_422(world: World, body: dict[str, str]) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _membership_id(owner, "Alpha Front_Desk")

    resp = owner.patch(f"{STAFF}/{membership_id}", json=body, headers=_csrf(owner))
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "REQ_VALIDATION_FAILED"


# --- Session events ---------------------------------------------------------------------------


def test_fr_aud_01_signing_in_and_out_is_recorded_with_the_session(
    world: World, session_factory: SessionFactory
) -> None:
    client = world.client_for(world.a.owner)
    signed_in = _events(session_factory, "auth.signed_in")
    assert len(signed_in) == 1
    assert signed_in[0]["actor_user_id"] == world.a.owner.id
    assert signed_in[0]["clinic_id"] is None  # a sign-in belongs to a user
    assert signed_in[0]["metadata"]["clinic_count"] == "1"
    session_id = signed_in[0]["metadata"]["session_id"]

    assert client.post("/api/v1/auth/sign-out", headers=_csrf(client)).status_code == 204
    signed_out = _events(session_factory, "auth.signed_out")
    assert len(signed_out) == 1
    assert signed_out[0]["metadata"]["session_id"] == session_id


def test_fr_aud_01_a_wrong_password_is_recorded_without_the_identifier(
    world: World, session_factory: SessionFactory
) -> None:
    assert world.a.owner.email is not None
    email = world.a.owner.email.value
    resp = world.anonymous().post(
        "/api/v1/auth/sign-in", json={"identifier": email, "password": "not-the-password"}
    )
    assert resp.status_code == 401

    failed = _events(session_factory, "auth.sign_in_failed")
    assert len(failed) == 1
    assert failed[0]["actor_user_id"] == world.a.owner.id
    assert failed[0]["metadata"] == {"reason": "wrong_password", "locked": "false"}
    assert email not in str(failed[0])


def test_an_unknown_identifier_is_not_recorded(
    world: World, session_factory: SessionFactory
) -> None:
    resp = world.anonymous().post(
        "/api/v1/auth/sign-in", json={"identifier": "nobody@example.test", "password": "x"}
    )
    assert resp.status_code == 401
    assert _events(session_factory) == []
