"""Role workspaces over HTTP on PostgreSQL (M6a-P6; FR-UX-01..06, FR-ORG-03, FR-ONB-08).

``doctor_id`` on ``/me``, Today's ``view``, *My Patients*, "my follow-ups", and the owner linked
as Doctor 1 by their invitation. A practising owner here is clinic A's owner with a doctor
profile linked through the existing ``POST /clinic/doctors`` (they are an active member).
"""

from __future__ import annotations

from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.test import TestResponse

from tests.conftest import World
from tests.integration.test_appointments_http import _patient
from tests.sessions_now import running_session

TODAY = "/api/v1/dashboard/today"
MINE = "/api/v1/my-patients"
SessionFactory = sessionmaker[Session]
PASSWORD = "a-new-owner-password"  # gitleaks:allow (synthetic test value)

OWNER_DOCTOR = {
    "display_name": "Dr. Alpha Owner",
    "qualification": "MBBS",
    "registration_number": "OWN-0001",
    "registration_council": "Sample State Medical Council",
}


def _send(client: FlaskClient, method: str, url: str, body: Any = None) -> TestResponse:
    csrf = client.get_cookie("me_csrf", path="/")
    headers = {"X-CSRF-Token": csrf.value} if csrf is not None else {}
    return client.open(url, method=method, json=body, headers=headers)


def _code(resp: TestResponse) -> str:
    return str(resp.get_json()["error"]["code"])


def _practising_owner(world: World) -> tuple[FlaskClient, str]:
    """Clinic A's owner with a doctor profile of their own; returns the client and its ID."""
    owner = world.client_for(world.a.owner)
    added = _send(
        owner, "POST", "/api/v1/clinic/doctors", {**OWNER_DOCTOR, "user_id": str(world.a.owner.id)}
    )
    assert added.status_code == 201, added.get_json()
    return owner, str(added.get_json()["id"])


def _seen(world: World, doctor: FlaskClient, session_id: str, name: str) -> str:
    """A patient booked into ``session_id`` (running now) and seen: the visit is started."""
    desk = world.client_for(world.a.desk)
    patient = _patient(desk, name)
    booked = _send(
        desk, "POST", "/api/v1/appointments", {"session_id": session_id, "patient_id": patient}
    )
    assert booked.status_code == 201, booked.get_json()
    appointment = booked.get_json()["id"]
    for seen, to in (("BOOKED", "ARRIVED"), ("ARRIVED", "IN_CONSULTATION")):
        moved = _send(
            desk,
            "POST",
            f"/api/v1/appointments/{appointment}/transitions",
            {"from": seen, "to": to},
        )
        assert moved.status_code == 200, moved.get_json()
    visit = _send(doctor, "POST", "/api/v1/visits", {"appointment_id": appointment})
    assert visit.status_code == 201, visit.get_json()
    return patient


def _membership(client: FlaskClient) -> dict[str, Any]:
    [membership] = client.get("/api/v1/me").get_json()["memberships"]
    return dict(membership)


# --- /me ---------------------------------------------------------------------------------------


def test_fr_ux_06_me_names_each_members_doctor_profile(world: World) -> None:
    assert _membership(world.client_for(world.a.doctor_user))["doctor_id"] == str(world.a.doctor.id)
    assert _membership(world.client_for(world.a.desk))["doctor_id"] is None
    assert _membership(world.client_for(world.a.owner))["doctor_id"] is None

    owner, profile = _practising_owner(world)

    mine = _membership(owner)
    assert (mine["role"], mine["doctor_id"]) == ("OWNER", profile)
    assert "CLINICAL_WRITE" in mine["permissions"]


# --- Today's view --------------------------------------------------------------------------------


def test_fr_ux_06_a_practising_owner_sees_only_their_own_day_in_the_doctor_view(
    world: World,
) -> None:
    owner, profile = _practising_owner(world)
    running_session(owner, profile)
    running_session(owner, world.a.doctor.id)

    clinic = owner.get(TODAY).get_json()
    doctor = owner.get(f"{TODAY}?view=doctor").get_json()

    assert clinic["scope"] == "CLINIC"
    assert {s["doctor_id"] for s in clinic["sessions"]} == {profile, str(world.a.doctor.id)}
    assert (doctor["scope"], doctor["doctor_id"]) == ("DOCTOR", profile)
    assert {s["doctor_id"] for s in doctor["sessions"]} == {profile}
    assert doctor["messages_failed"] is None
    assert owner.get(f"{TODAY}?view=clinic").get_json()["scope"] == "CLINIC"


@pytest.mark.parametrize("who", ["owner", "desk"])
def test_the_doctor_view_needs_a_doctor_profile(world: World, who: str) -> None:
    resp = world.client_for(getattr(world.a, who)).get(f"{TODAY}?view=doctor")
    assert resp.status_code == 409
    assert _code(resp) == "CLN_NO_DOCTOR_PROFILE"


def test_a_doctor_always_gets_their_own_day_and_an_unknown_view_is_refused(world: World) -> None:
    doctor = world.client_for(world.a.doctor_user)
    assert doctor.get(f"{TODAY}?view=clinic").get_json()["scope"] == "DOCTOR"
    bad = doctor.get(f"{TODAY}?view=everyone")
    assert bad.status_code == 422
    assert _code(bad) == "REQ_VALIDATION_FAILED"


# --- My Patients ---------------------------------------------------------------------------------


def test_fr_ux_02_my_patients_lists_only_the_patients_this_doctor_saw(world: World) -> None:
    owner, profile = _practising_owner(world)
    doctor = world.client_for(world.a.doctor_user)
    session = running_session(owner, world.a.doctor.id)["id"]
    first = _seen(world, doctor, session, "Mine First")
    second = _seen(world, doctor, session, "Mine Second")
    _seen(world, owner, running_session(owner, profile)["id"], "Owner Patient")
    _patient(world.client_for(world.a.desk), "Never Seen")

    resp = doctor.get(MINE)

    assert resp.status_code == 200, resp.get_json()
    assert resp.headers["Cache-Control"] == "no-store"
    body = resp.get_json()
    assert [p["id"] for p in body["items"]] == [second, first]  # latest visit first
    assert (body["limit"], body["offset"]) == (50, 0)
    item = body["items"][0]
    assert set(item) == {
        "id",
        "code",
        "full_name",
        "sex",
        "age_years",
        "age_is_estimated",
        "last_visit_at",
        "visits",
    }
    assert item["visits"] == 1

    # The practising owner sees their own, not the colleague's.
    assert [p["full_name"] for p in owner.get(MINE).get_json()["items"]] == ["Owner Patient"]
    # q narrows by name prefix; a page can be asked for.
    assert [p["id"] for p in doctor.get(f"{MINE}?q=mine f").get_json()["items"]] == [first]
    assert doctor.get(f"{MINE}?limit=1&offset=1").get_json()["items"][0]["id"] == first


def test_my_patients_is_for_doctors(world: World) -> None:
    desk = world.client_for(world.a.desk).get(MINE)
    assert desk.status_code == 403 and _code(desk) == "PERM_DENIED"
    owner = world.client_for(world.a.owner).get(MINE)
    assert owner.status_code == 409 and _code(owner) == "CLN_NO_DOCTOR_PROFILE"
    bad = world.client_for(world.a.doctor_user).get(f"{MINE}?limit=0")
    assert bad.status_code == 422


def test_nfr_08_another_clinics_visits_never_appear(world: World) -> None:
    doctor_b = world.client_for(world.b.doctor_user)
    _seen_b = _send(doctor_b, "GET", MINE)
    assert _seen_b.status_code == 200
    doctor_a = world.client_for(world.a.doctor_user)
    session = running_session(world.client_for(world.a.owner), world.a.doctor.id)["id"]
    _seen(world, doctor_a, session, "Alpha Only")
    assert all(p["full_name"] != "Alpha Only" for p in doctor_b.get(MINE).get_json()["items"])


# --- My follow-ups -------------------------------------------------------------------------------


def test_pending_follow_ups_can_be_kept_to_one_doctor(world: World) -> None:
    desk = world.client_for(world.a.desk)
    ok = desk.get(f"/api/v1/follow-ups/pending?doctor_id={world.a.doctor.id}")
    assert ok.status_code == 200
    assert all(i["doctor_id"] == str(world.a.doctor.id) for i in ok.get_json()["items"])
    bad = desk.get("/api/v1/follow-ups/pending?doctor_id=not-an-id")
    assert bad.status_code == 422


# --- Owner as Doctor 1 (decision 8A) -------------------------------------------------------------


def _ops_clinic_with_doctor(world: World) -> tuple[FlaskClient, str, str]:
    ops = world.client_for(world.ops)
    clinic = _send(
        ops,
        "POST",
        "/api/v1/ops/clinics",
        {"name": "Solo Sample Clinic", "slug": "solo-sample", "phone": "9000012399"},
    )
    assert clinic.status_code == 201, clinic.get_json()
    clinic_id = clinic.get_json()["id"]
    doctor = _send(ops, "POST", f"/api/v1/ops/clinics/{clinic_id}/doctors", OWNER_DOCTOR)
    assert doctor.status_code == 201, doctor.get_json()
    return ops, clinic_id, str(doctor.get_json()["id"])


def test_fr_onb_08_the_owners_invitation_links_doctor_1_and_accepting_makes_it_count(
    world: World, session_factory: SessionFactory
) -> None:
    ops, clinic_id, doctor_id = _ops_clinic_with_doctor(world)

    invited = _send(
        ops,
        "POST",
        f"/api/v1/ops/clinics/{clinic_id}/staff-invites",
        {
            "full_name": "Dr. Solo Owner",
            "role": "OWNER",
            "email": "solo.owner@example.test",
            "doctor_id": doctor_id,
        },
    )

    assert invited.status_code == 201, invited.get_json()
    token = invited.get_json()["accept_url"].rsplit("/", 1)[1]
    with session_factory() as session:
        linked = session.execute(
            text("SELECT user_id FROM doctors WHERE id = :id"), {"id": doctor_id}
        ).scalar_one()
        events = session.execute(
            text("SELECT action, metadata FROM audit_events WHERE entity_id = :id"),
            {"id": doctor_id},
        ).all()
    assert str(linked) == invited.get_json()["user_id"]
    assert ("doctor.updated", "owner_invite") in {(a, m.get("via")) for a, m in events}

    owner = world.anonymous()
    accepted = _send(owner, "POST", f"/api/v1/auth/invites/{token}/accept", {"password": PASSWORD})
    assert accepted.status_code == 200, accepted.get_json()
    mine = _membership(owner)
    assert (mine["role"], mine["doctor_id"]) == ("OWNER", doctor_id)
    assert "CLINICAL_WRITE" in mine["permissions"]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"role": "DOCTOR"}, "only an owner's invitation"),
        ({"doctor_id": "0192f0a0-0000-7000-8000-0000000000ff"}, "active doctor of this clinic"),
    ],
    ids=["not-owner", "unknown-doctor"],
)
def test_doctor_id_on_an_invitation_is_refused_when_it_does_not_fit(
    world: World, change: dict[str, str], reason: str
) -> None:
    ops, clinic_id, doctor_id = _ops_clinic_with_doctor(world)
    body = {
        "full_name": "Dr. Solo Owner",
        "role": "OWNER",
        "email": "solo.owner@example.test",
        "doctor_id": doctor_id,
        **change,
    }

    resp = _send(ops, "POST", f"/api/v1/ops/clinics/{clinic_id}/staff-invites", body)

    assert resp.status_code == 422
    [problem] = resp.get_json()["error"]["details"]["fields"]
    assert problem["field"] == "doctor_id" and reason in problem["reason"]


def test_a_doctor_already_linked_to_someone_else_cannot_be_doctor_1(world: World) -> None:
    owner = world.client_for(world.a.owner)
    resp = _send(
        owner,
        "POST",
        "/api/v1/clinic/staff",
        {
            "full_name": "Second Owner",
            "role": "OWNER",
            "phone": "9000077501",
            "doctor_id": str(world.a.doctor.id),
        },
    )
    assert resp.status_code == 422
    assert "already linked" in resp.get_json()["error"]["details"]["fields"][0]["reason"]
