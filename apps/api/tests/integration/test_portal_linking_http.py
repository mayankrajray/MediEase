"""Linking patient accounts and the portal's reads over HTTP (M6b-P1; patient portal spec).

FR-PRT-02, 03, 06 (b, c); NFR-18; R1-R14; AC1-AC6. Real PostgreSQL, the real composition root.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from tests.conftest import World
from tests.integration.test_patient_links_http import _last4, _link, _token, _wrong
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_prescriptions_http import _issued
from tests.integration.test_visits_http import _send
from tests.portal_helpers import (
    PORTAL,
    accept,
    invite,
    invite_token,
    link_by_invite,
    link_by_prescription,
    portal_client,
    verify_email,
)

EMAIL = "linking.patient@example.test"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _register(staff: FlaskClient, name: str, phone: str, *, confirm_new: bool = False) -> str:
    resp = _send(
        staff,
        "POST",
        "/api/v1/patients",
        {
            "full_name": name,
            "phone": phone,
            "sex": "UNDISCLOSED",
            "date_of_birth": "1990-05-17",
            "confirm_new": confirm_new,
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["id"])


def _patient(staff: FlaskClient, patient_id: str) -> dict[str, Any]:
    body: dict[str, Any] = staff.get(f"/api/v1/patients/{patient_id}").get_json()
    return body


def _status(staff: FlaskClient, patient_id: str) -> dict[str, Any]:
    resp = staff.get(f"/api/v1/patients/{patient_id}/portal")
    assert resp.status_code == 200, resp.get_json()
    body: dict[str, Any] = resp.get_json()
    return body


def _code(resp: Any) -> str:
    return str(resp.get_json()["error"]["code"])


def _audit(db: Engine) -> list[tuple[str, str, dict[str, Any]]]:
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, actor_type, metadata FROM audit_events"
                " WHERE action LIKE 'patient.portal_%' OR action LIKE 'patient_link.%'"
                " ORDER BY occurred_at, id"
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


def _count_audit(db: Engine) -> int:
    with db.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one())


def _verified(world: World, db: Engine, email: str = EMAIL) -> FlaskClient:
    client = portal_client(world, email)
    verify_email(db, email)
    return client


# --- Invites (R1-R4, AC1) ------------------------------------------------------------------------


def test_ac1_fr_prt_06b_an_invite_links_the_record_once(world: World, db: Engine) -> None:
    owner = world.client_for(world.a.owner)
    patient_id = _register(owner, "Asha Rao", "9000000201")
    code = _patient(owner, patient_id)["code"]
    created = invite(owner, patient_id)
    assert created.status_code == 201, created.get_json()
    body = created.get_json()
    assert body["url"].startswith("http") and "/portal/link/" in body["url"]
    token = body["url"].rsplit("/portal/link/", 1)[1]
    assert _status(owner, patient_id)["status"] == "INVITED"

    patient = portal_client(world, EMAIL)
    described = patient.get(f"{PORTAL}/invites/{token}")
    assert described.status_code == 200
    assert described.get_json() == {
        "clinic_name": "Alpha Sample Clinic",
        "patient_first_name": "Asha",
        "patient_code": code,
    }
    linked = accept(patient, token)
    assert linked.status_code == 201, linked.get_json()
    assert (linked.get_json()["method"], linked.get_json()["patient_code"]) == ("INVITE", code)

    links = patient.get(f"{PORTAL}/links").get_json()["items"]
    assert [(i["clinic"]["name"], i["patient_first_name"], i["patient_code"]) for i in links] == [
        ("Alpha Sample Clinic", "Asha", code)
    ]
    again = accept(patient, token)
    assert (again.status_code, _code(again)) == (404, "PRT_INVITE_INVALID")
    status = _status(owner, patient_id)
    assert (status["status"], status["method"]) == ("LINKED", "INVITE")
    assert "email" not in str(status)

    events = _audit(db)
    assert [(a, t) for a, t, _ in events] == [
        ("patient.portal_invited", "STAFF"),
        ("patient.portal_linked", "PATIENT"),
    ]
    assert events[1][2]["method"] == "INVITE"
    assert EMAIL not in str(events) and "Asha" not in str(events)


def test_r2_superseded_expired_and_unknown_invites_get_one_answer(world: World, db: Engine) -> None:
    owner = world.client_for(world.a.owner)
    patient_id = _register(owner, "Asha Rao", "9000000202")
    old = invite_token(owner, patient_id)
    new = invite_token(owner, patient_id)
    patient = portal_client(world, EMAIL)
    for token in (old, "x" * 43, "y" * 300):
        resp = patient.get(f"{PORTAL}/invites/{token}")
        assert (resp.status_code, _code(resp)) == (404, "PRT_INVITE_INVALID"), token
        assert _code(accept(patient, token)) == "PRT_INVITE_INVALID"
    assert patient.get(f"{PORTAL}/invites/{new}").status_code == 200

    with db.begin() as conn:
        conn.execute(text("UPDATE patient_portal_invites SET expires_at = now() - interval '1s'"))
    assert _code(patient.get(f"{PORTAL}/invites/{new}")) == "PRT_INVITE_INVALID"
    assert _status(owner, patient_id)["status"] == "NOT_LINKED"


def test_r4_a_record_or_an_account_links_once_per_clinic(world: World) -> None:
    owner = world.client_for(world.a.owner)
    first = _register(owner, "Asha Rao", "9000000203")
    second = _register(owner, "Bina Shah", "9000000204")
    asha = portal_client(world, EMAIL)
    link_by_invite(owner, asha, first)

    # The linked record cannot be invited again.
    refused = invite(owner, first)
    assert (refused.status_code, _code(refused)) == (409, "PRT_ALREADY_LINKED")
    # The account already has a record here: refused, and the invite stays for the right person.
    token = invite_token(owner, second)
    resp = accept(asha, token)
    assert (resp.status_code, _code(resp)) == (409, "PRT_ALREADY_LINKED")
    bina = portal_client(world, "bina.patient@example.test", name="Bina Shah")
    assert accept(bina, token).status_code == 201


# --- Prescription link (R5, R6, AC2) -------------------------------------------------------------


def test_ac2_fr_prt_06c_a_prescription_link_links_only_a_verified_account(
    world: World, db: Engine
) -> None:
    _, visit, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    right = _last4(world, visit["patient_id"])

    unverified = portal_client(world, "unverified.patient@example.test")
    resp = link_by_prescription(unverified, token, right)
    assert (resp.status_code, _code(resp)) == (403, "PRT_UNVERIFIED_ACCOUNT")
    assert unverified.get(f"{PORTAL}/links").get_json()["items"] == []

    patient = _verified(world, db)
    wrong = link_by_prescription(patient, token, _wrong(right))
    assert (wrong.status_code, _code(wrong)) == (401, "LINK_CHALLENGE_FAILED")
    assert wrong.get_json()["error"]["details"]["attempts_left"] == "4"
    linked = link_by_prescription(patient, token, right)
    assert linked.status_code == 201, linked.get_json()
    assert linked.get_json()["method"] == "RX_LINK"
    assert [i["method"] for i in patient.get(f"{PORTAL}/links").get_json()["items"]] == ["RX_LINK"]
    owner = world.client_for(world.a.owner)
    assert _status(owner, visit["patient_id"])["method"] == "RX_LINK"
    # The right answer cleared the count; no page was opened, so no open was counted.
    page = world.client_for(world.a.desk).get(f"/api/v1/prescriptions/{rx['id']}/link")
    assert (page.get_json()["locked"], page.get_json()["open_count"]) == (False, 0)
    actions = [(a, t) for a, t, _ in _audit(db) if t == "PATIENT"]
    assert actions == [
        ("patient_link.challenge_failed", "PATIENT"),
        ("patient.portal_linked", "PATIENT"),
    ]


def test_r6_five_wrong_answers_in_the_portal_lock_the_link_for_the_page_too(
    world: World, db: Engine
) -> None:
    _, visit, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    wrong = _wrong(_last4(world, visit["patient_id"]))
    patient = _verified(world, db)
    codes = [_code(link_by_prescription(patient, token, wrong)) for _ in range(5)]
    assert codes == ["LINK_CHALLENGE_FAILED"] * 4 + ["LINK_LOCKED"]
    right = link_by_prescription(patient, token, _last4(world, visit["patient_id"]))
    assert (right.status_code, _code(right)) == (423, "LINK_LOCKED")
    assert world.anonymous().get(f"/api/v1/public/links/{token}").get_json()["locked"] is True
    assert ("patient_link.locked", "PATIENT") in [(a, t) for a, t, _ in _audit(db)]
    assert patient.get(f"{PORTAL}/links").get_json()["items"] == []


# --- What a link grants (R9-R13, AC3, AC5) -------------------------------------------------------


def _reminder(owner: FlaskClient, world: World, patient_id: str) -> str:
    url = f"/api/v1/patients/{patient_id}"
    consent = _send(owner, "PUT", f"{url}/consent", {"whatsapp": True, "sms": False})
    assert consent.status_code == 200, consent.get_json()
    created = _send(
        owner,
        "POST",
        f"{url}/reminders",
        {
            "doctor_id": str(world.a.doctor.id),
            "follow_up_date": (date.today() + timedelta(days=12)).isoformat(),
        },
    )
    assert created.status_code in (200, 201), created.get_json()
    return str(created.get_json()["id"])


def test_ac3_fr_prt_03_a_linked_account_reads_its_record_and_nothing_clinical(
    world: World, db: Engine
) -> None:
    doctor, visit, rx = _issued(world)
    owner = world.client_for(world.a.owner)
    patient = portal_client(world, EMAIL)
    link_by_invite(owner, patient, visit["patient_id"])
    reminders_before = {
        r["id"]
        for r in owner.get(f"/api/v1/patients/{visit['patient_id']}/reminders").get_json()["items"]
    }
    reminder_id = _reminder(owner, world, visit["patient_id"])
    before = _count_audit(db)

    groups = patient.get(f"{PORTAL}/appointments").get_json()["items"]
    assert [g["clinic_name"] for g in groups] == ["Alpha Sample Clinic"]
    [appointment] = groups[0]["appointments"]
    assert appointment["id"] == visit["appointment_id"]
    assert set(appointment) == {
        "id",
        "doctor_name",
        "on_date",
        "starts_at",
        "session_starts_at",
        "session_ends_at",
        "mode",
        "slot_start",
        "token_number",
        "status",
    }
    assert appointment["status"] == "IN_CONSULTATION"

    listed = patient.get(f"{PORTAL}/prescriptions").get_json()["items"]
    assert [(p["id"], p["version"]) for p in listed] == [(rx["id"], 1)]
    page = patient.get(f"{PORTAL}/prescriptions/{rx['id']}?lang=hi")
    assert page.status_code == 200 and page.get_json()["language"] == "hi"
    assert page.get_json()["medicines"]
    pdf = patient.get(f"{PORTAL}/prescriptions/{rx['id']}/pdf")
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf"
    assert pdf.headers["Cache-Control"] == "no-store"

    reminders = patient.get(f"{PORTAL}/reminders").get_json()["items"]
    assert reminder_id in {r["id"] for r in reminders}
    assert {r["id"] for r in reminders} == reminders_before | {reminder_id}
    assert set(reminders[0]) == {
        "id",
        "clinic_id",
        "clinic_name",
        "kind",
        "follow_up_date",
        "due_at",
        "status",
    }
    # Reading the portal writes no audit rows (decision 7A).
    assert _count_audit(db) == before

    # A revision's draft is never shown; the issued version still is.
    draft = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise")
    assert draft.status_code == 201, draft.get_json()
    resp = patient.get(f"{PORTAL}/prescriptions/{draft.get_json()['id']}")
    assert (resp.status_code, _code(resp)) == (404, "REQ_NOT_FOUND")
    assert patient.get(f"{PORTAL}/prescriptions/{draft.get_json()['id']}/pdf").status_code == 404
    assert [p["id"] for p in patient.get(f"{PORTAL}/prescriptions").get_json()["items"]] == [
        rx["id"]
    ]
    # The clinic's own phone is on the group (a call button, M6b-P2); no patient's phone anywhere.
    assert set(groups[0]) == {"clinic_id", "clinic_name", "timezone", "phone_e164", "appointments"}
    for body in (groups[0]["appointments"], listed, reminders):
        for word in ("notes", "diagnosis", "vitals", "reason", "findings", "phone_e164"):
            assert f'"{word}"' not in str(body).replace("'", '"')


def test_ac5_two_patients_sharing_a_phone_stay_apart(world: World) -> None:
    owner = world.client_for(world.a.owner)
    asha = _register(owner, "Asha Rao", "9000000205")
    meena = _register(owner, "Meena Rao", "9000000205", confirm_new=True)
    patient = portal_client(world, EMAIL)
    link_by_invite(owner, patient, asha)
    links = patient.get(f"{PORTAL}/links").get_json()["items"]
    assert [i["patient_first_name"] for i in links] == ["Asha"]
    assert meena not in patient.get(f"{PORTAL}/appointments").text
    assert _status(owner, meena)["status"] == "NOT_LINKED"


# --- Unlinking (R8, AC6) -------------------------------------------------------------------------


def test_ac6_r8_a_link_ended_by_staff_hides_the_clinic_at_once(world: World, db: Engine) -> None:
    _, visit, rx = _issued(world)
    owner = world.client_for(world.a.owner)
    patient = portal_client(world, EMAIL)
    link_by_invite(owner, patient, visit["patient_id"])
    assert patient.get(f"{PORTAL}/prescriptions/{rx['id']}").status_code == 200

    ended = _send(owner, "DELETE", f"/api/v1/patients/{visit['patient_id']}/portal-link")
    assert ended.status_code == 200 and ended.get_json()["status"] == "NOT_LINKED"
    assert patient.get(f"{PORTAL}/links").get_json()["items"] == []
    assert patient.get(f"{PORTAL}/appointments").get_json()["items"] == []
    resp = patient.get(f"{PORTAL}/prescriptions/{rx['id']}")
    assert (resp.status_code, _code(resp)) == (404, "REQ_NOT_FOUND")
    again = _send(owner, "DELETE", f"/api/v1/patients/{visit['patient_id']}/portal-link")
    assert (again.status_code, _code(again)) == (404, "REQ_NOT_FOUND")
    unlinked = [m for a, t, m in _audit(db) if a == "patient.portal_unlinked"]
    assert [m["by"] for m in unlinked] == ["STAFF"]


def test_r8_the_patient_unlinks_and_can_be_invited_again(world: World, db: Engine) -> None:
    owner = world.client_for(world.a.owner)
    patient_id = _register(owner, "Asha Rao", "9000000206")
    patient = portal_client(world, EMAIL)
    link_id = link_by_invite(owner, patient, patient_id)["id"]

    ended = patient.delete(f"{PORTAL}/links/{link_id}", headers=portal_csrf(patient))
    assert ended.status_code == 200, ended.get_json()
    assert patient.get(f"{PORTAL}/links").get_json()["items"] == []
    gone = patient.delete(f"{PORTAL}/links/{link_id}", headers=portal_csrf(patient))
    assert (gone.status_code, _code(gone)) == (404, "REQ_NOT_FOUND")
    assert _status(owner, patient_id)["status"] == "NOT_LINKED"
    assert [(a, t) for a, t, _ in _audit(db)][-1] == ("patient.portal_unlinked", "PATIENT")
    # History is kept and a new link can be made.
    link_by_invite(owner, patient, patient_id)
    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT revoked_by FROM patient_account_links ORDER BY created_at")
        ).all()
    assert [r[0] for r in rows] == ["PATIENT", None]


def test_a_suspended_clinic_shows_nothing_until_it_is_active_again(
    world: World, db: Engine
) -> None:
    owner = world.client_for(world.a.owner)
    patient_id = _register(owner, "Asha Rao", "9000000207")
    patient = portal_client(world, EMAIL)
    link_by_invite(owner, patient, patient_id)
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinics SET status = 'SUSPENDED' WHERE id = :id"),
            {"id": world.a.clinic.id},
        )
    assert patient.get(f"{PORTAL}/links").get_json()["items"] == []
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinics SET status = 'ACTIVE' WHERE id = :id"), {"id": world.a.clinic.id}
        )
    assert len(patient.get(f"{PORTAL}/links").get_json()["items"]) == 1
