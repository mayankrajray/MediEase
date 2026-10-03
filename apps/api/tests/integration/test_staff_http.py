"""Owner management of staff, doctors and clinic settings (FR-ORG-01/02/04; R7, R9, R11).

The role change landed in M1-P4; this covers the rest of what an owner can do
to their own clinic, and what the rules refuse.
"""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.test import TestResponse

from tests.conftest import UowFactory, World

CLINIC = "/api/v1/clinic"
DOCTORS = "/api/v1/clinic/doctors"
STAFF = "/api/v1/clinic/staff"
SessionFactory = sessionmaker[Session]

DOCTOR_BODY = {
    "display_name": "Dr. Added Sample",
    "qualification": "MBBS",
    "registration_number": "ADD-0001",
    "registration_council": "Sample State Medical Council",
}


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def _post(client: FlaskClient, path: str, body: dict[str, Any]) -> TestResponse:
    return client.post(path, json=body, headers=_csrf(client))


def _patch(client: FlaskClient, path: str, body: dict[str, Any]) -> TestResponse:
    return client.patch(path, json=body, headers=_csrf(client))


def _membership_id(client: FlaskClient, full_name: str) -> str:
    staff = client.get(STAFF).get_json()["items"]
    return str(next(m["membership_id"] for m in staff if m["full_name"] == full_name))


def _events(session_factory: SessionFactory, action: str) -> list[dict[str, Any]]:
    with session_factory() as session:
        rows = session.execute(
            text("SELECT * FROM audit_events WHERE action = :action ORDER BY occurred_at"),
            {"action": action},
        )
        return [dict(row) for row in rows.mappings()]


# --- Staff ------------------------------------------------------------------------------------


def test_ac4_fr_org_04_deactivating_a_member_ends_their_access_next_request(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)
    desk = world.client_for(world.a.desk)
    assert desk.get(CLINIC).status_code == 200

    resp = _patch(
        owner, f"{STAFF}/{_membership_id(owner, 'Alpha Front_Desk')}", {"status": "DEACTIVATED"}
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "DEACTIVATED"

    refused = desk.get(CLINIC)
    assert refused.status_code == 403
    assert refused.get_json()["error"]["code"] == "AUTH_ACCOUNT_DISABLED"

    events = _events(session_factory, "staff.deactivated")
    assert len(events) == 1
    assert events[0]["actor_user_id"] == world.a.owner.id
    assert events[0]["metadata"]["target_user_id"] == str(world.a.desk.id)
    assert events[0]["metadata"]["from_status"] == "ACTIVE"


def test_r9_the_last_owner_cannot_be_deactivated(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)
    resp = _patch(
        owner, f"{STAFF}/{_membership_id(owner, 'Alpha Owner')}", {"status": "DEACTIVATED"}
    )

    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CLN_LAST_OWNER"
    assert _events(session_factory, "staff.deactivated") == []


def test_a_deactivated_member_cannot_be_deactivated_again(world: World) -> None:
    owner = world.client_for(world.a.owner)
    membership = f"{STAFF}/{_membership_id(owner, 'Alpha Doctor')}"
    assert _patch(owner, membership, {"status": "DEACTIVATED"}).status_code == 200

    again = _patch(owner, membership, {"status": "DEACTIVATED"})
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "CLN_INVALID_TRANSITION"


@pytest.mark.parametrize(
    "body",
    [{}, {"status": "ACTIVE"}, {"status": "INVITED"}, {"role": "OWNER", "extra": 1}],
    ids=["nothing", "reactivate", "re-invite", "unknown-field"],
)
def test_an_unsupported_membership_change_is_422(world: World, body: dict[str, Any]) -> None:
    """Reactivation is not in M1: the lifecycle has no way back (spec §3)."""
    owner = world.client_for(world.a.owner)
    resp = _patch(owner, f"{STAFF}/{_membership_id(owner, 'Alpha Doctor')}", body)
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "REQ_VALIDATION_FAILED"


def test_a_role_and_a_status_can_be_sent_together(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)
    resp = _patch(
        owner,
        f"{STAFF}/{_membership_id(owner, 'Alpha Doctor')}",
        {"role": "FRONT_DESK", "status": "DEACTIVATED"},
    )

    assert resp.status_code == 200
    assert (resp.get_json()["role"], resp.get_json()["status"]) == ("FRONT_DESK", "DEACTIVATED")
    # Each change is its own audit action.
    assert len(_events(session_factory, "staff.role_changed")) == 1
    assert len(_events(session_factory, "staff.deactivated")) == 1


def test_only_an_owner_can_invite_or_deactivate(world: World) -> None:
    doctor = world.client_for(world.a.doctor_user)
    invite = _post(doctor, STAFF, {"full_name": "X", "role": "DOCTOR", "email": "x@example.test"})
    assert invite.status_code == 403
    assert invite.get_json()["error"]["code"] == "PERM_DENIED"


# --- Doctors ----------------------------------------------------------------------------------


def test_fr_org_02_an_owner_adds_and_corrects_a_doctor(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)

    added = _post(owner, DOCTORS, DOCTOR_BODY)
    assert added.status_code == 201
    doctor = added.get_json()
    assert doctor["registration_number"] == "ADD-0001"
    assert doctor["is_active"] is True

    updated = _patch(
        owner, f"{DOCTORS}/{doctor['id']}", {"qualification": "MBBS, MS", "specialty": "ENT"}
    )
    assert updated.status_code == 200
    assert updated.get_json()["qualification"] == "MBBS, MS"
    assert updated.get_json()["display_name"] == "Dr. Added Sample"  # untouched

    assert [e["metadata"]["fields"] for e in _events(session_factory, "doctor.updated")] == [
        "qualification,specialty"
    ]


def test_a_doctor_can_be_linked_only_to_a_member_of_this_clinic(world: World) -> None:
    owner = world.client_for(world.a.owner)
    stranger = {**DOCTOR_BODY, "user_id": str(world.b.doctor_user.id)}

    resp = _post(owner, DOCTORS, stranger)
    assert resp.status_code == 422
    fields = resp.get_json()["error"]["details"]["fields"]
    assert fields == [{"field": "user_id", "reason": "must be an active member of this clinic"}]

    # Spec §8: the owner's own account can hold a doctor profile too.
    allowed = _post(owner, DOCTORS, {**DOCTOR_BODY, "user_id": str(world.a.owner.id)})
    assert allowed.status_code == 201
    assert allowed.get_json()["user_id"] == str(world.a.owner.id)


def test_one_doctor_profile_per_account_is_a_field_error_not_a_crash(world: World) -> None:
    """The clinic's doctor already has a profile; linking a second one is refused clearly."""
    owner = world.client_for(world.a.owner)
    resp = _post(owner, DOCTORS, {**DOCTOR_BODY, "user_id": str(world.a.doctor_user.id)})

    assert resp.status_code == 422
    assert resp.get_json()["error"]["details"]["fields"] == [
        {"field": "user_id", "reason": "already has a doctor profile in this clinic"}
    ]


def test_an_existing_doctor_profile_can_be_relinked_to_its_own_account(world: World) -> None:
    owner = world.client_for(world.a.owner)
    resp = _patch(
        owner,
        f"{DOCTORS}/{world.a.doctor.id}",
        {"user_id": str(world.a.doctor_user.id), "specialty": "ENT"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["specialty"] == "ENT"


def test_a_doctor_is_deactivated_through_the_same_patch(world: World) -> None:
    owner = world.client_for(world.a.owner)
    resp = _patch(owner, f"{DOCTORS}/{world.a.doctor.id}", {"is_active": False})

    assert resp.status_code == 200
    assert resp.get_json()["is_active"] is False
    # Still listed: history refers to them (the list is not filtered in M1).
    assert str(world.a.doctor.id) in owner.get(DOCTORS).text


def test_adding_a_doctor_without_registration_details_is_422(world: World) -> None:
    owner = world.client_for(world.a.owner)
    incomplete = {k: v for k, v in DOCTOR_BODY.items() if k != "registration_number"}
    assert _post(owner, DOCTORS, incomplete).status_code == 422


def test_only_clinic_management_can_add_a_doctor(world: World) -> None:
    desk = world.client_for(world.a.desk)
    assert _post(desk, DOCTORS, DOCTOR_BODY).status_code == 403
    assert desk.get(DOCTORS).status_code == 200  # reading is every role's


# --- Clinic settings --------------------------------------------------------------------------


def test_fr_org_01_an_owner_edits_their_clinic(
    world: World, session_factory: SessionFactory
) -> None:
    owner = world.client_for(world.a.owner)
    resp = _patch(owner, CLINIC, {"name": "Alpha Renamed Clinic", "city": "New City"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert (body["name"], body["city"]) == ("Alpha Renamed Clinic", "New City")
    assert body["slug"] == world.a.clinic.slug  # not editable
    assert [e["metadata"]["fields"] for e in _events(session_factory, "clinic.updated")] == [
        "name,city"
    ]


@pytest.mark.parametrize(
    "body",
    [{}, {"slug": "new-slug"}, {"timezone": "Mars/Olympus"}, {"pincode": "12"}],
    ids=["nothing", "slug", "bad-timezone", "bad-pincode"],
)
def test_an_invalid_clinic_edit_is_422(world: World, body: dict[str, Any]) -> None:
    owner = world.client_for(world.a.owner)
    assert _patch(owner, CLINIC, body).status_code == 422


def test_the_front_desk_cannot_edit_the_clinic(world: World) -> None:
    desk = world.client_for(world.a.desk)
    resp = _patch(desk, CLINIC, {"name": "Not Allowed"})
    assert resp.status_code == 403
    assert resp.get_json()["error"]["details"]["permission"] == "CLINIC_MANAGE"


def test_every_write_needs_the_csrf_header(world: World, uow_factory: UowFactory) -> None:
    owner = world.client_for(world.a.owner)
    assert owner.patch(CLINIC, json={"name": "No CSRF"}).status_code == 403
    assert owner.post(DOCTORS, json=DOCTOR_BODY).status_code == 403
    with uow_factory() as uow:
        stored = uow.clinics.get(world.a.clinic.id)
    assert stored is not None and stored.name == "Alpha Sample Clinic"


def test_another_clinics_membership_cannot_be_deactivated(world: World) -> None:
    owner_of_b = world.client_for(world.b.owner)
    membership_in_b = _membership_id(owner_of_b, "Beta Front_Desk")

    owner_of_a = world.client_for(world.a.owner)
    resp = _patch(owner_of_a, f"{STAFF}/{membership_in_b}", {"status": "DEACTIVATED"})
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "REQ_NOT_FOUND"


def test_another_clinics_doctor_cannot_be_edited(world: World) -> None:
    owner_of_a = world.client_for(world.a.owner)
    resp = _patch(owner_of_a, f"{DOCTORS}/{world.b.doctor.id}", {"specialty": "ENT"})
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "REQ_NOT_FOUND"


def test_a_doctor_id_that_is_not_a_uuid_is_404(world: World) -> None:
    owner = world.client_for(world.a.owner)
    assert owner.get(f"{DOCTORS}/not-a-uuid").status_code == 404
