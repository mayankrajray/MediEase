"""The daily queue over HTTP on PostgreSQL (M3-P3; FR-QUE-01, 02, 04; spec R9-R11, AC3).

Decisions D17-D22. Today's tests use a session running now (``tests/sessions_now.py``), because
the queue only moves on the session's day and the app runs on the system clock.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from tests.conftest import World
from tests.integration.test_appointments_http import _in_parallel, _patient
from tests.sessions_now import running_session

KOLKATA = ZoneInfo("Asia/Kolkata")


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


def _move(client: FlaskClient, appointment_id: str, seen: str, to: str) -> TestResponse:
    return _send(
        client,
        "POST",
        f"/api/v1/appointments/{appointment_id}/transitions",
        {"from": seen, "to": to},
    )


def _book(client: FlaskClient, session_id: str, patient_id: str, **extra: object) -> str:
    resp = _send(
        client,
        "POST",
        "/api/v1/appointments",
        {"session_id": session_id, "patient_id": patient_id, **extra},
    )
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["id"])


def _walk_in(client: FlaskClient, world: World, patient_id: str, **extra: object) -> TestResponse:
    return _send(
        client,
        "POST",
        "/api/v1/queue/walk-ins",
        {"doctor_id": str(world.a.doctor.id), "patient_id": patient_id, **extra},
    )


def _audit(db: Engine, action: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT metadata FROM audit_events WHERE action = :a ORDER BY occurred_at"),
            {"a": action},
        ).all()
    return [r[0] for r in rows]


# --- Transitions (R9, AC3, D18) -------------------------------------------------------------------


def test_fr_que_02_a_patient_moves_through_the_day(world: World, db: Engine) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    appointment = _book(desk, session["id"], _patient(desk))

    arrived = _move(desk, appointment, "BOOKED", "ARRIVED")
    assert arrived.status_code == 200, arrived.get_json()
    assert arrived.get_json()["arrived_at"] is not None
    doctor = world.client_for(world.a.doctor_user)
    assert _move(doctor, appointment, "ARRIVED", "IN_CONSULTATION").get_json()["started_at"]
    done = _move(doctor, appointment, "IN_CONSULTATION", "COMPLETED")
    assert (done.get_json()["status"], done.get_json()["completed_at"] is not None) == (
        "COMPLETED",
        True,
    )

    back = _move(desk, appointment, "COMPLETED", "ARRIVED")  # AC3
    assert (back.status_code, _code(back)) == (409, "QUE_INVALID_TRANSITION")
    assert back.get_json()["error"]["details"] == {"from": "COMPLETED", "to": "ARRIVED"}

    history = desk.get(f"/api/v1/appointments/{appointment}").get_json()["history"]
    assert [h["to_status"] for h in history] == [
        "BOOKED",
        "ARRIVED",
        "IN_CONSULTATION",
        "COMPLETED",
    ]
    changes = _audit(db, "appointment.status_changed")
    assert [(c["from"], c["to"]) for c in changes] == [
        ("BOOKED", "ARRIVED"),
        ("ARRIVED", "IN_CONSULTATION"),
        ("IN_CONSULTATION", "COMPLETED"),
    ]
    assert changes[0]["session_id"] == session["id"]


def test_d18_two_tabs_making_the_same_move_one_wins(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    session = running_session(owner, world.a.doctor.id)
    appointment = _book(desk, session["id"], _patient(desk))

    results = _in_parallel(
        [
            lambda: _move(desk, appointment, "BOOKED", "ARRIVED"),
            lambda: _move(doctor, appointment, "BOOKED", "NO_SHOW"),
        ]
    )

    assert sorted(r.status_code for r in results) == [200, 409]
    loser = next(r for r in results if r.status_code == 409)
    assert _code(loser) == "QUE_INVALID_TRANSITION"
    winner = next(r for r in results if r.status_code == 200).get_json()["status"]
    assert loser.get_json()["error"]["details"]["from"] == winner


def test_d19_no_show_and_late_arrival_and_cancelled_is_not_a_transition(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    appointment = _book(desk, session["id"], _patient(desk))

    assert _move(desk, appointment, "BOOKED", "NO_SHOW").status_code == 200
    late = _move(desk, appointment, "NO_SHOW", "ARRIVED")
    assert (late.status_code, late.get_json()["status"]) == (200, "ARRIVED")
    cancelled = _move(desk, appointment, "ARRIVED", "CANCELLED")
    assert (cancelled.status_code, _code(cancelled)) == (409, "QUE_INVALID_TRANSITION")
    bad = _send(desk, "POST", f"/api/v1/appointments/{appointment}/transitions", {"to": "ARRIVED"})
    assert (bad.status_code, _code(bad)) == (422, "REQ_VALIDATION_FAILED")


def test_d19_an_appointment_next_week_cannot_move_today(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    blocks = [
        {"weekday": d, "start_time": "10:00", "end_time": "13:00", "capacity": 5} for d in range(7)
    ]
    url = f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule"
    assert _send(owner, "PUT", url, {"blocks": blocks}).status_code == 200
    later = (datetime.now(KOLKATA).date() + timedelta(days=7)).isoformat()
    session = desk.get(f"/api/v1/sessions?date={later}").get_json()["items"][0]
    appointment = _book(desk, session["id"], _patient(desk))

    resp = _move(desk, appointment, "BOOKED", "ARRIVED")
    assert (resp.status_code, _code(resp)) == (409, "QUE_WRONG_TIME")
    assert resp.get_json()["error"]["details"] == {"reason": "not_today"}


# --- Walk-ins (R11, D21) --------------------------------------------------------------------------


def test_fr_que_04_a_walk_in_arrives_at_once_with_the_next_token(world: World, db: Engine) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id, capacity=2)
    _book(desk, session["id"], _patient(desk))

    walk_in = _walk_in(desk, world, _patient(desk, "Bina Shah"))
    assert walk_in.status_code == 201, walk_in.get_json()
    body = walk_in.get_json()
    assert (body["status"], body["source"], body["token_number"], body["session_id"]) == (
        "ARRIVED",
        "WALK_IN",
        2,
        session["id"],
    )
    assert body["arrived_at"] is not None
    history = desk.get(f"/api/v1/appointments/{body['id']}").get_json()["history"]
    assert [(h["from_status"], h["to_status"]) for h in history] == [
        (None, "BOOKED"),
        ("BOOKED", "ARRIVED"),
    ]
    assert _audit(db, "appointment.booked")[-1]["source"] == "WALK_IN"

    full = _walk_in(desk, world, _patient(desk, "Chetan Iyer"))
    assert (full.status_code, _code(full)) == (409, "APT_SESSION_FULL")


def test_r11_a_slot_mode_walk_in_takes_the_earliest_free_slot(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    assert _send(owner, "PATCH", "/api/v1/clinic", {"booking_mode": "SLOTS"}).status_code == 200
    session = running_session(owner, world.a.doctor.id, slot=15)
    now = datetime.now(KOLKATA)
    open_slots = [s for s in session["slots"] if datetime.fromisoformat(s["ends_at"]) > now]
    _book(desk, session["id"], _patient(desk), slot_start=open_slots[0]["starts_at"])

    walk_in = _walk_in(desk, world, _patient(desk, "Bina Shah"))
    assert walk_in.status_code == 201, walk_in.get_json()
    assert walk_in.get_json()["slot_start"] == open_slots[1]["starts_at"]


def test_d21_no_session_left_today_is_a_clear_error(world: World) -> None:
    desk = world.client_for(world.a.desk)
    resp = _walk_in(desk, world, _patient(desk))
    assert (resp.status_code, _code(resp)) == (409, "QUE_NO_SESSION")


def test_nfr_08_a_walk_in_for_another_clinics_doctor_or_patient_is_404(world: World) -> None:
    owner_a, owner_b = world.client_for(world.a.owner), world.client_for(world.b.owner)
    running_session(owner_a, world.a.doctor.id)
    stranger = _walk_in(owner_a, world, _patient(owner_b))
    assert (stranger.status_code, stranger.get_json()["error"]["details"]) == (
        404,
        {"entity": "patient"},
    )
    other_doctor = _send(
        owner_a,
        "POST",
        "/api/v1/queue/walk-ins",
        {"doctor_id": str(world.b.doctor.id), "patient_id": _patient(owner_a)},
    )
    assert (other_doctor.status_code, other_doctor.get_json()["error"]["details"]) == (
        404,
        {"entity": "doctor"},
    )


# --- The day's queue (FR-QUE-01, D22) -------------------------------------------------------------


def test_fr_que_01_the_queue_lists_today_in_token_order_with_patients(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    asha = _book(desk, session["id"], _patient(desk, "Asha Rao"))
    bina = _book(desk, session["id"], _patient(desk, "Bina Shah"))
    chetan = _book(desk, session["id"], _patient(desk, "Chetan Iyer"))
    assert _move(desk, bina, "BOOKED", "ARRIVED").status_code == 200
    cancelled = _send(
        desk, "POST", f"/api/v1/appointments/{chetan}/cancel", {"reason": "DUPLICATE"}
    )
    assert cancelled.status_code == 200

    resp = desk.get(f"/api/v1/queue?doctor_id={world.a.doctor.id}")
    assert resp.status_code == 200, resp.get_json()
    assert resp.headers["Cache-Control"] == "no-store"
    queue = resp.get_json()
    assert queue["on_date"] == datetime.now(KOLKATA).date().isoformat()
    [today] = queue["sessions"]
    assert today["id"] == session["id"]
    rows = today["appointments"]
    assert [(r["id"], r["token_number"], r["patient"]["full_name"]) for r in rows] == [
        (asha, 1, "Asha Rao"),
        (bina, 2, "Bina Shah"),
    ]
    assert rows[0]["wait_minutes"] is None and rows[1]["wait_minutes"] == 0
    assert rows[0]["patient"]["code"] and rows[0]["patient"]["age_years"] >= 30

    everything = desk.get("/api/v1/queue?include_cancelled=true").get_json()
    assert [r["status"] for r in everything["sessions"][0]["appointments"]][-1] == "CANCELLED"


def test_the_queue_for_a_quiet_day_is_empty_and_far_dates_are_refused(world: World) -> None:
    desk = world.client_for(world.a.desk)
    assert desk.get("/api/v1/queue").get_json()["sessions"] == []
    far = (datetime.now(KOLKATA).date() + timedelta(days=200)).isoformat()
    refused = desk.get(f"/api/v1/queue?date={far}")
    assert (refused.status_code, _code(refused)) == (422, "REQ_VALIDATION_FAILED")
