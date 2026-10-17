"""Visits over HTTP on PostgreSQL (M4-P1; FR-VIS-01..03, 05; spec prescriptions R1-R3, R16, R17).

AC6 (the 24-hour lock), AC9 (one audit row per consultation view), AC7 for visits (no clinical
text in logs, audit rows or errors), the permissions of spec §2 and decisions 1A-6A. The app runs
on the system clock, so a consultation happens in a session running now
(``tests/sessions_now.py``) and "25 hours later" is set in the database (the CHECK keeps
``locked_at = completed_at + 24 h``).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DBAPIError
from werkzeug.test import TestResponse

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession, Session
from mediease_api.domain.visits.visit import Visit, VisitStatus
from mediease_api.domain.visits.vitals import Vitals
from tests.builders import NOW, a_doctor, new_id
from tests.conftest import UowFactory, World
from tests.integration.test_appointments_http import _in_parallel, _patient
from tests.sessions_now import running_session

VISITS = "/api/v1/visits"
SENTINEL = "SENTINEL-clinical-7f3a"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _send(client: FlaskClient, method: str, url: str, body: Any = None) -> TestResponse:
    csrf = client.get_cookie("me_csrf", path="/")
    headers = {"X-CSRF-Token": csrf.value} if csrf is not None else {}
    return client.open(url, method=method, json=body, headers=headers)


def _code(resp: TestResponse) -> str:
    return str(resp.get_json()["error"]["code"])


def _move(client: FlaskClient, appointment_id: str, seen: str, to: str) -> None:
    resp = _send(
        client,
        "POST",
        f"/api/v1/appointments/{appointment_id}/transitions",
        {"from": seen, "to": to},
    )
    assert resp.status_code == 200, resp.get_json()


def _in_consultation(world: World, *, status: str = "IN_CONSULTATION") -> tuple[str, str]:
    """Book a patient into a session running now and walk them to ``status``."""
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    patient = _patient(desk)
    booked = _send(
        desk, "POST", "/api/v1/appointments", {"session_id": session["id"], "patient_id": patient}
    )
    assert booked.status_code == 201, booked.get_json()
    appointment = str(booked.get_json()["id"])
    if status in ("ARRIVED", "IN_CONSULTATION"):
        _move(desk, appointment, "BOOKED", "ARRIVED")
    if status == "IN_CONSULTATION":
        _move(desk, appointment, "ARRIVED", "IN_CONSULTATION")
    return appointment, patient


def _start(doctor: FlaskClient, appointment: str) -> TestResponse:
    return _send(doctor, "POST", VISITS, {"appointment_id": appointment})


def _started(world: World) -> tuple[FlaskClient, dict[str, Any]]:
    appointment, _ = _in_consultation(world)
    doctor = world.client_for(world.a.doctor_user)
    resp = _start(doctor, appointment)
    assert resp.status_code == 201, resp.get_json()
    return doctor, resp.get_json()


def _audit(db: Engine, *actions: str) -> list[tuple[str, dict[str, Any]]]:
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, metadata FROM audit_events WHERE action = ANY(:a)"
                " ORDER BY occurred_at, id"
            ),
            {"a": list(actions)},
        ).all()
    return [(r[0], r[1]) for r in rows]


def _past_visit(uow_factory: UowFactory, world: World, patient_id: str, days_ago: int) -> UUID:
    """A completed visit on an earlier day, written through the repositories (history data)."""
    starts = NOW - timedelta(days=days_ago)
    clinic_id, doctor_id = world.a.clinic.id, world.a.doctor.id
    plan = PlannedSession(
        doctor_id, starts.date(), starts, starts + timedelta(hours=3), BookingMode.TOKENS, None, 5
    )
    with uow_factory() as uow:
        staff = uow.tenant(clinic_id)
        session = Session.from_plan(plan, id=new_id(), clinic_id=clinic_id, now=starts)
        staff.sessions.add_missing([session])
        appointment = Appointment.book(
            session, id=new_id(), patient_id=UUID(patient_id), active=[], now=starts
        )
        staff.sessions.update(session)
        staff.appointments.add(appointment)
        visit = Visit(
            id=new_id(),
            clinic_id=clinic_id,
            patient_id=UUID(patient_id),
            doctor_id=doctor_id,
            appointment_id=appointment.id,
            status=VisitStatus.OPEN,
            chief_complaint=f"earlier complaint {days_ago}",
            findings=None,
            diagnosis=f"earlier diagnosis {days_ago}",
            notes=None,
            vitals=Vitals.empty(),
            revision=1,
            started_at=starts,
            completed_at=None,
            locked_at=None,
            created_by=world.a.doctor_user.id,
            created_at=starts,
            updated_at=starts,
        )
        staff.visits.add(visit)
        visit.complete(starts + timedelta(minutes=10))
        staff.visits.update(visit)
        uow.commit()
    return visit.id


# --- Start (R1, decisions 1A and 5A) -------------------------------------------------------------


def test_fr_vis_01_the_doctor_starts_the_visit_once_per_appointment(
    world: World, db: Engine
) -> None:
    appointment, patient = _in_consultation(world)
    doctor = world.client_for(world.a.doctor_user)

    first = _start(doctor, appointment)
    assert first.status_code == 201, first.get_json()
    visit = first.get_json()
    assert (visit["appointment_id"], visit["patient_id"], visit["doctor_id"]) == (
        appointment,
        patient,
        str(world.a.doctor.id),
    )
    assert (visit["status"], visit["revision"], visit["is_locked"], visit["addenda"]) == (
        "OPEN",
        1,
        False,
        [],
    )
    assert first.headers["Cache-Control"] == "no-store"

    again = _start(doctor, appointment)
    assert (again.status_code, _code(again)) == (409, "VIS_ALREADY_EXISTS")
    assert again.get_json()["error"]["details"] == {"visit_id": visit["id"]}
    [(_, started)] = _audit(db, "visit.started")
    assert started == {
        "appointment_id": appointment,
        "patient_id": patient,
        "doctor_id": str(world.a.doctor.id),
    }


@pytest.mark.parametrize("status", ["BOOKED", "ARRIVED"])
def test_r1_a_visit_starts_only_in_consultation(world: World, status: str) -> None:
    appointment, _ = _in_consultation(world, status=status)
    resp = _start(world.client_for(world.a.doctor_user), appointment)
    assert (resp.status_code, _code(resp)) == (409, "VIS_NOT_STARTABLE")
    assert resp.get_json()["error"]["details"] == {"status": status}


def test_r1_two_starts_at_once_make_one_visit(world: World) -> None:
    appointment, _ = _in_consultation(world)
    doctor = world.client_for(world.a.doctor_user)
    results = _in_parallel(
        [lambda: _start(doctor, appointment), lambda: _start(doctor, appointment)]
    )
    assert sorted(r.status_code for r in results) == [201, 409]
    loser = next(r for r in results if r.status_code == 409)
    winner = next(r for r in results if r.status_code == 201)
    assert loser.get_json()["error"]["details"]["visit_id"] == winner.get_json()["id"]


# --- Edit (FR-VIS-02, decision 4A) ---------------------------------------------------------------


def test_fr_vis_02_edit_sends_only_what_changed_and_a_stale_tab_is_refused(
    world: World, db: Engine
) -> None:
    doctor, visit = _started(world)
    url = f"{VISITS}/{visit['id']}"

    edited = _send(
        doctor,
        "PATCH",
        url,
        {"revision": 1, "chief_complaint": "fever", "vitals": {"temp_c": 38.4, "pulse": 96}},
    )
    assert edited.status_code == 200, edited.get_json()
    body = edited.get_json()
    assert (body["chief_complaint"], body["vitals"], body["revision"]) == (
        "fever",
        {"pulse": 96, "temp_c": 38.4},
        2,
    )

    stale = _send(doctor, "PATCH", url, {"revision": 1, "notes": "from the other tab"})
    assert (stale.status_code, _code(stale)) == (409, "VIS_STALE")
    assert stale.get_json()["error"]["details"] == {"revision": "2"}

    cleared = _send(doctor, "PATCH", url, {"revision": 2, "chief_complaint": None})
    assert (cleared.get_json()["chief_complaint"], cleared.get_json()["revision"]) == (None, 3)
    unchanged = _send(doctor, "PATCH", url, {"revision": 3, "notes": "  "})
    assert unchanged.get_json()["revision"] == 3

    bad = _send(doctor, "PATCH", url, {"revision": 3, "vitals": {"temp_c": 370}})
    assert (bad.status_code, _code(bad)) == (422, "REQ_VALIDATION_FAILED")
    assert bad.get_json()["error"]["details"]["fields"][0]["field"] == "vitals.temp_c"
    unknown = _send(doctor, "PATCH", url, {"revision": 3, "status": "COMPLETED"})
    assert (unknown.status_code, _code(unknown)) == (422, "REQ_VALIDATION_FAILED")

    updates = [m for _, m in _audit(db, "visit.updated")]
    assert updates == [
        {"fields": "chief_complaint,vitals", "revision": "2"},
        {"fields": "chief_complaint", "revision": "3"},
    ]


# --- Complete, the lock and addenda (R3, AC6, decisions 2A, 3A, 6A) ------------------------------


def test_decision_2a_completing_the_visit_completes_the_appointment(
    world: World, db: Engine
) -> None:
    doctor, visit = _started(world)
    done = _send(doctor, "POST", f"{VISITS}/{visit['id']}/complete")
    assert done.status_code == 200, done.get_json()
    body = done.get_json()
    assert body["status"] == "COMPLETED" and body["is_locked"] is False
    assert body["locked_at"] is not None and body["completed_at"] is not None

    desk = world.client_for(world.a.desk)
    appointment = desk.get(f"/api/v1/appointments/{visit['appointment_id']}").get_json()
    assert appointment["status"] == "COMPLETED"
    assert [h["to_status"] for h in appointment["history"]][-1] == "COMPLETED"

    again = _send(doctor, "POST", f"{VISITS}/{visit['id']}/complete")
    assert (again.status_code, again.get_json()["completed_at"]) == (200, body["completed_at"])
    actions = _audit(db, "visit.completed", "appointment.status_changed")
    assert [a for a, _ in actions][-2:] == ["visit.completed", "appointment.status_changed"]
    assert actions[-1][1]["by"] == "visit.completed"
    assert len([a for a, _ in actions if a == "visit.completed"]) == 1


def test_decision_2a_a_queue_move_first_leaves_the_visit_open(world: World) -> None:
    doctor, visit = _started(world)
    _move(world.client_for(world.a.desk), visit["appointment_id"], "IN_CONSULTATION", "COMPLETED")
    record = doctor.get(f"{VISITS}/{visit['id']}").get_json()["visit"]
    assert record["status"] == "OPEN"
    done = _send(doctor, "POST", f"{VISITS}/{visit['id']}/complete")
    assert done.get_json()["status"] == "COMPLETED"


def test_ac6_a_visit_completed_25_hours_ago_is_locked_and_takes_an_addendum(
    world: World, db: Engine
) -> None:
    doctor, visit = _started(world)
    url = f"{VISITS}/{visit['id']}"
    early = _send(doctor, "POST", f"{url}/addenda", {"body": "too soon"})
    assert (early.status_code, _code(early)) == (409, "VIS_NOT_COMPLETED")
    assert _send(doctor, "POST", f"{url}/complete").status_code == 200
    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE visits SET completed_at = now() - interval '25 hours',"
                " locked_at = now() - interval '1 hour' WHERE id = :id"
            ),
            {"id": visit["id"]},
        )

    current = doctor.get(url).get_json()["visit"]
    assert current["is_locked"] is True
    locked = _send(doctor, "PATCH", url, {"revision": current["revision"], "notes": "late"})
    assert (locked.status_code, _code(locked)) == (409, "VIS_LOCKED")

    added = _send(doctor, "POST", f"{url}/addenda", {"body": "  lab result reviewed "})
    assert added.status_code == 201, added.get_json()
    note = added.get_json()
    assert (note["body"], note["author_user_id"]) == (
        "lab result reviewed",
        str(world.a.doctor_user.id),
    )
    assert [a["id"] for a in doctor.get(url).get_json()["visit"]["addenda"]] == [note["id"]]
    [(_, meta)] = _audit(db, "visit.addendum_added")
    assert meta == {"addendum_id": note["id"], "after_lock": "true"}

    for statement in ("UPDATE visit_addenda SET body = 'x'", "DELETE FROM visit_addenda"):
        with pytest.raises(DBAPIError, match="VIS_ADDENDUM_APPEND_ONLY"), db.begin() as conn:
            conn.execute(text(statement))


# --- Reads: the consultation view, history and its audit (R2, R16, AC9) --------------------------


def test_r16_ac9_the_consultation_view_is_one_read_and_one_audit_row(
    world: World, db: Engine, uow_factory: UowFactory
) -> None:
    appointment, patient = _in_consultation(world)
    older = [_past_visit(uow_factory, world, patient, days) for days in (30, 3)]
    doctor = world.client_for(world.a.doctor_user)
    visit = _start(doctor, appointment).get_json()
    _send(doctor, "PATCH", f"{VISITS}/{visit['id']}", {"revision": 1, "notes": "today"})

    view = doctor.get(f"{VISITS}/{visit['id']}")
    assert view.status_code == 200, view.get_json()
    body = view.get_json()
    assert (body["visit"]["notes"], body["patient"]["id"]) == ("today", patient)
    assert [h["id"] for h in body["history"]] == [str(older[1]), str(older[0])]  # newest first
    assert body["history"][0]["diagnosis"] == "earlier diagnosis 3"
    assert view.headers["Cache-Control"] == "no-store"

    [(_, meta)] = _audit(db, "visit.viewed")
    assert meta == {"patient_id": patient, "history": "2"}
    doctor.get(f"{VISITS}/{visit['id']}")
    assert len(_audit(db, "visit.viewed")) == 2  # one per open, none for the PATCH or start


def test_fr_vis_03_a_patients_visits_page_newest_first_with_one_audit_row(
    world: World, db: Engine, uow_factory: UowFactory
) -> None:
    desk = world.client_for(world.a.desk)
    patient = _patient(desk)
    ids = [_past_visit(uow_factory, world, patient, days) for days in (9, 7, 5)]
    owner = world.client_for(world.a.owner)  # an owner reads clinical records (§2)

    first = owner.get(f"/api/v1/patients/{patient}/visits?limit=2")
    assert first.status_code == 200, first.get_json()
    page = first.get_json()
    assert [v["id"] for v in page["items"]] == [str(ids[2]), str(ids[1])]
    assert page["next_before"] == str(ids[1])
    rest = owner.get(f"/api/v1/patients/{patient}/visits?limit=2&before={page['next_before']}")
    assert ([v["id"] for v in rest.get_json()["items"]], rest.get_json()["next_before"]) == (
        [str(ids[0])],
        None,
    )
    assert [m for _, m in _audit(db, "patient.visits_viewed")] == [{"count": "2"}, {"count": "1"}]

    for query in ("limit=0", "limit=51", "limit=ten", f"before={new_id()}"):
        bad = owner.get(f"/api/v1/patients/{patient}/visits?{query}")
        assert (bad.status_code, _code(bad)) == (422, "REQ_VALIDATION_FAILED"), query


# --- Who may (spec §2, decision 3A, NFR-08) ------------------------------------------------------


def test_d4_front_desk_never_sees_or_writes_a_visit(world: World) -> None:
    _, visit = _started(world)
    desk = world.client_for(world.a.desk)
    one = f"{VISITS}/{visit['id']}"
    calls = [
        ("GET", one, None),
        ("PATCH", one, {"revision": 1, "notes": "x"}),
        ("POST", f"{one}/complete", None),
        ("POST", f"{one}/addenda", {"body": "x"}),
        ("POST", VISITS, {"appointment_id": visit["appointment_id"]}),
        ("GET", f"/api/v1/patients/{visit['patient_id']}/visits", None),
    ]
    for method, url, body in calls:
        resp = _send(desk, method, url, body)
        assert (resp.status_code, _code(resp)) == (403, "PERM_DENIED"), (method, url)


def test_d4_an_owner_reads_but_only_the_visits_doctor_writes(
    world: World, uow_factory: UowFactory
) -> None:
    _, visit = _started(world)
    owner = world.client_for(world.a.owner)
    one = f"{VISITS}/{visit['id']}"
    assert owner.get(one).status_code == 200
    plain = _send(owner, "PATCH", one, {"revision": 1, "notes": "x"})
    assert (plain.status_code, _code(plain)) == (403, "PERM_DENIED")

    # The owner becomes a doctor too (CLINICAL_WRITE), but this is not their visit.
    with uow_factory() as uow:
        uow.tenant(world.a.clinic.id).doctors.add(
            a_doctor(world.a.clinic.id, user_id=world.a.owner.id)
        )
        uow.commit()
    owner = world.client_for(world.a.owner)
    for method, url, body in (
        ("PATCH", one, {"revision": 1, "notes": "x"}),
        ("POST", f"{one}/complete", None),
        ("POST", VISITS, {"appointment_id": visit["appointment_id"]}),
    ):
        resp = _send(owner, method, url, body)
        assert (resp.status_code, _code(resp)) == (403, "VIS_NOT_YOURS"), (method, url)


def test_nfr_08_another_clinics_visit_and_history_are_not_found(world: World) -> None:
    _, visit = _started(world)
    other = world.client_for(world.b.doctor_user)
    one = f"{VISITS}/{visit['id']}"
    for method, url, body in (
        ("GET", one, None),
        ("PATCH", one, {"revision": 1, "notes": "x"}),
        ("POST", f"{one}/complete", None),
        ("POST", f"{one}/addenda", {"body": "x"}),
        ("POST", VISITS, {"appointment_id": visit["appointment_id"]}),
        ("GET", f"/api/v1/patients/{visit['patient_id']}/visits", None),
    ):
        resp = _send(other, method, url, body)
        assert resp.status_code in (403, 404), (method, url, resp.get_json())
        assert _code(resp) in ("REQ_NOT_FOUND", "VIS_NOT_YOURS"), (method, url)
    # Reads are plain not-found: nothing says the visit exists.
    assert _code(other.get(one)) == "REQ_NOT_FOUND"


# --- AC7 for visits: no clinical text outside the record (R17) -----------------------------------


def test_r17_clinical_text_never_reaches_logs_audit_or_errors(
    world: World, db: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    doctor, visit = _started(world)
    url = f"{VISITS}/{visit['id']}"
    capsys.readouterr()

    fields = {k: f"{SENTINEL} {k}" for k in ("chief_complaint", "findings", "diagnosis", "notes")}
    assert _send(doctor, "PATCH", url, {"revision": 1, **fields}).status_code == 200
    too_long = _send(doctor, "PATCH", url, {"revision": 2, "notes": SENTINEL + "x" * 5000})
    assert too_long.status_code == 422
    assert _send(doctor, "POST", f"{url}/complete").status_code == 200
    assert (
        _send(doctor, "POST", f"{url}/addenda", {"body": f"{SENTINEL} addendum"}).status_code == 201
    )
    doctor.get(url)
    doctor.get(f"/api/v1/patients/{visit['patient_id']}/visits")

    logged = capsys.readouterr().out
    assert SENTINEL not in logged
    assert "visit.updated" in logged and "visit.addendum_added" in logged
    assert SENTINEL not in str(too_long.get_json())
    with db.connect() as conn:
        leaked = conn.execute(
            text("SELECT count(*) FROM audit_events WHERE metadata::text LIKE :s"),
            {"s": f"%{SENTINEL}%"},
        ).scalar()
    assert leaked == 0
