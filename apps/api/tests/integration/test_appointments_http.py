"""Booking, cancel and reschedule over HTTP on PostgreSQL (M3-P2; FR-APT-03..05, FR-APT-07).

Spec R3-R8, AC1, AC2; decisions D10-D15. The concurrency tests run real threads against real
row locks: the guarantees under test are the database's, not timing's.

Like the scheduling suite, dates come from the clinic's today (Asia/Kolkata): every test works on
the Monday at least a week ahead.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from tests.conftest import World

KOLKATA = ZoneInfo("Asia/Kolkata")


def _next_monday() -> date:
    today = datetime.now(KOLKATA).date()
    return today + timedelta(days=7 + (7 - today.weekday()) % 7)


MONDAY = _next_monday()
TUESDAY = MONDAY + timedelta(days=1)
TEN = f"{MONDAY.isoformat()}T04:30:00+00:00"  # 10:00 in Kolkata
ELEVEN = f"{MONDAY.isoformat()}T05:30:00+00:00"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _send(client: FlaskClient, method: str, url: str, body: Any = None) -> TestResponse:
    csrf = client.get_cookie("me_csrf", path="/")
    headers = {"X-CSRF-Token": csrf.value} if csrf is not None else {}
    return client.open(url, method=method, json=body, headers=headers)


def _schedule(world: World, *, capacity: int = 12, slot: int = 60, mode: str = "TOKENS") -> None:
    """Monday and Tuesday 10:00-13:00 for clinic A's doctor, usable in either mode."""
    owner = world.client_for(world.a.owner)
    if mode == "SLOTS":
        assert _send(owner, "PATCH", "/api/v1/clinic", {"booking_mode": "SLOTS"}).status_code == 200
    blocks = [
        {
            "weekday": d,
            "start_time": "10:00",
            "end_time": "13:00",
            "slot_minutes": slot,
            "capacity": capacity,
        }
        for d in (0, 1)
    ]
    resp = _send(
        owner, "PUT", f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule", {"blocks": blocks}
    )
    assert resp.status_code == 200, resp.get_json()


def _session(client: FlaskClient, world: World, on: date = MONDAY) -> dict[str, Any]:
    resp = client.get(f"/api/v1/sessions?date={on.isoformat()}&doctor_id={world.a.doctor.id}")
    assert resp.status_code == 200, resp.get_json()
    [session] = resp.get_json()["items"]
    return session  # type: ignore[no-any-return]


_phones = iter(range(9000000200, 9000000999))


def _patient(client: FlaskClient, name: str = "Asha Rao") -> str:
    resp = _send(
        client,
        "POST",
        "/api/v1/patients",
        {
            "full_name": name,
            "phone": str(next(_phones)),
            "sex": "UNDISCLOSED",
            "date_of_birth": "1990-05-17",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["id"])


def _book(client: FlaskClient, session_id: str, patient_id: str, **extra: object) -> TestResponse:
    return _send(
        client,
        "POST",
        "/api/v1/appointments",
        {"session_id": session_id, "patient_id": patient_id, **extra},
    )


def _code(resp: TestResponse) -> str:
    return str(resp.get_json()["error"]["code"])


def _scalar(db: Engine, sql: str, **params: object) -> Any:
    with db.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _audit(db: Engine, action: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT metadata FROM audit_events WHERE action = :a ORDER BY occurred_at"),
            {"a": action},
        ).all()
    return [r[0] for r in rows]


def _in_parallel(calls: list[Callable[[], TestResponse]]) -> list[TestResponse]:
    """Run the calls at once from a barrier; every thread starts before any waits."""
    barrier = threading.Barrier(len(calls), timeout=15)
    results: list[TestResponse | None] = [None] * len(calls)

    def run(i: int) -> None:
        barrier.wait()
        results[i] = calls[i]()

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(calls))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert all(r is not None for r in results), "a request did not finish (deadlock?)"
    return [r for r in results if r is not None]


def _consistent(db: Engine) -> None:
    """booked_count always equals the session's active appointments (design note "Risks")."""
    drift = _scalar(
        db,
        "SELECT count(*) FROM sessions s WHERE s.booked_count <> (SELECT count(*) FROM"
        " appointments a WHERE a.session_id = s.id AND a.status <> 'CANCELLED')",
    )
    assert drift == 0


# --- Token mode (R4, R5, AC2) --------------------------------------------------------------------


def test_ac2_fr_apt_03_tokens_book_in_order_and_are_never_reused(world: World, db: Engine) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    patients = [_patient(desk, f"Patient {i}") for i in range(4)]

    first, second, third = (_book(desk, session["id"], p) for p in patients[:3])
    assert [r.status_code for r in (first, second, third)] == [201, 201, 201]
    assert [r.get_json()["token_number"] for r in (first, second, third)] == [1, 2, 3]
    body = first.get_json()
    assert (body["status"], body["source"], body["slot_start"], body["on_date"]) == (
        "BOOKED",
        "FRONT_DESK",
        None,
        MONDAY.isoformat(),
    )

    cancelled = _send(
        desk,
        "POST",
        f"/api/v1/appointments/{second.get_json()['id']}/cancel",
        {"reason": "PATIENT_REQUEST", "note": "  "},
    )
    assert cancelled.status_code == 200, cancelled.get_json()
    assert (cancelled.get_json()["status"], cancelled.get_json()["cancel_reason"]) == (
        "CANCELLED",
        "PATIENT_REQUEST",
    )

    fourth = _book(desk, session["id"], patients[3])
    assert fourth.get_json()["token_number"] == 4
    after = _session(desk, world)
    assert (after["booked_count"], after["available"], after["next_token"]) == (3, 9, 5)
    _consistent(db)

    booked = _audit(db, "appointment.booked")
    assert len(booked) == 4
    assert booked[0] == {
        "session_id": session["id"],
        "doctor_id": str(world.a.doctor.id),
        "patient_id": patients[0],
        "mode": "TOKENS",
        "source": "FRONT_DESK",
        "token_number": "1",
    }
    [cancel_row] = _audit(db, "appointment.cancelled")
    assert cancel_row["cancel_reason"] == "PATIENT_REQUEST"
    assert cancel_row["from_status"] == "BOOKED"
    assert "Patient" not in str([*booked, cancel_row])


def test_r5_a_full_session_and_d13_the_same_patient_twice(world: World) -> None:
    _schedule(world, capacity=1)
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    asha, bina = _patient(desk), _patient(desk, "Bina Shah")

    first = _book(desk, session["id"], asha)
    assert first.status_code == 201
    again = _book(desk, session["id"], asha)
    assert (again.status_code, _code(again)) == (409, "APT_ALREADY_BOOKED")
    assert again.get_json()["error"]["details"] == {"appointment_id": first.get_json()["id"]}
    full = _book(desk, session["id"], bina)
    assert (full.status_code, _code(full)) == (409, "APT_SESSION_FULL")


def test_every_role_books_and_the_source_and_reason_are_recorded(world: World, db: Engine) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    for user, source in ((world.a.owner, "PHONE"), (world.a.doctor_user, "WHATSAPP")):
        client = world.client_for(user)
        resp = _book(client, session["id"], _patient(client), source=source, reason="follow-up")
        assert resp.status_code == 201, resp.get_json()
        assert (resp.get_json()["source"], resp.get_json()["reason"]) == (source, "follow-up")
    assert "follow-up" not in str(_audit(db, "appointment.booked"))

    walk_in = _book(desk, session["id"], _patient(desk), source="WALK_IN")
    assert (walk_in.status_code, _code(walk_in)) == (422, "REQ_VALIDATION_FAILED")
    long = _book(desk, session["id"], _patient(desk), reason="x" * 121)
    assert long.status_code == 422
    with_slot = _book(desk, session["id"], _patient(desk), slot_start=TEN)
    assert (with_slot.status_code, _code(with_slot)) == (422, "REQ_VALIDATION_FAILED")


def test_d12_r6_a_session_that_has_ended_is_in_the_past(world: World, db: Engine) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE sessions SET starts_at = now() - interval '3 hours',"
                " ends_at = now() - interval '1 minute' WHERE id = :id"
            ),
            {"id": session["id"]},
        )
    resp = _book(desk, session["id"], _patient(desk))
    assert (resp.status_code, _code(resp)) == (422, "APT_IN_PAST")


# --- Slot mode (R3, R6) --------------------------------------------------------------------------


def test_r3_slots_show_availability_and_hold_one_appointment_each(world: World, db: Engine) -> None:
    _schedule(world, mode="SLOTS", slot=60)
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    assert [s["available"] for s in session["slots"]] == [True, True, True]
    asha, bina = _patient(desk), _patient(desk, "Bina Shah")

    # Sent in the clinic's offset, compared as an instant.
    booked = _book(desk, session["id"], asha, slot_start=f"{MONDAY.isoformat()}T10:00:00+05:30")
    assert booked.status_code == 201, booked.get_json()
    assert (booked.get_json()["slot_start"], booked.get_json()["token_number"]) == (TEN, None)
    assert [s["available"] for s in _session(desk, world)["slots"]] == [False, True, True]

    taken = _book(desk, session["id"], bina, slot_start=TEN)
    assert (taken.status_code, _code(taken)) == (409, "APT_SLOT_TAKEN")
    off_grid = _book(desk, session["id"], bina, slot_start=f"{MONDAY.isoformat()}T05:00:00Z")
    assert (off_grid.status_code, _code(off_grid)) == (422, "APT_OUTSIDE_SCHEDULE")
    missing = _book(desk, session["id"], bina)
    assert (missing.status_code, _code(missing)) == (422, "REQ_VALIDATION_FAILED")
    assert _book(desk, session["id"], bina, slot_start=ELEVEN).status_code == 201
    _consistent(db)

    [row] = [r for r in _audit(db, "appointment.booked") if r["patient_id"] == asha]
    assert (row["mode"], row["slot_start"]) == ("SLOTS", TEN)


# --- Concurrency (FR-APT-04, AC1) ----------------------------------------------------------------


def test_ac1_fr_apt_04_two_parallel_bookings_of_the_last_place_one_wins(
    world: World, db: Engine
) -> None:
    _schedule(world, capacity=1)
    desk, doctor = world.client_for(world.a.desk), world.client_for(world.a.doctor_user)
    session = _session(desk, world)
    asha, bina = _patient(desk), _patient(desk, "Bina Shah")

    results = _in_parallel(
        [lambda: _book(desk, session["id"], asha), lambda: _book(doctor, session["id"], bina)]
    )

    assert sorted(r.status_code for r in results) == [201, 409]
    [loser] = [r for r in results if r.status_code == 409]
    assert _code(loser) == "APT_SESSION_FULL"
    assert _scalar(db, "SELECT booked_count FROM sessions WHERE id = :id", id=session["id"]) == 1
    _consistent(db)


def test_ac1_two_parallel_bookings_of_one_slot_one_wins(world: World, db: Engine) -> None:
    _schedule(world, mode="SLOTS", slot=60)
    desk, doctor = world.client_for(world.a.desk), world.client_for(world.a.doctor_user)
    session = _session(desk, world)
    asha, bina = _patient(desk), _patient(desk, "Bina Shah")

    results = _in_parallel(
        [
            lambda: _book(desk, session["id"], asha, slot_start=TEN),
            lambda: _book(doctor, session["id"], bina, slot_start=TEN),
        ]
    )

    assert sorted(r.status_code for r in results) == [201, 409]
    assert _code(next(r for r in results if r.status_code == 409)) == "APT_SLOT_TAKEN"
    assert _scalar(db, "SELECT booked_count FROM sessions WHERE id = :id", id=session["id"]) == 1


def test_fr_apt_04_fifteen_parallel_bookings_fill_twelve_tokens_without_gaps(
    world: World, db: Engine
) -> None:
    _schedule(world, capacity=12)
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    patients = [_patient(desk, f"Patient {i}") for i in range(15)]
    clients = [world.client_for(world.a.desk) for _ in patients]

    results = _in_parallel(
        [
            (lambda c=c, p=p: _book(c, session["id"], p))  # type: ignore[misc]
            for c, p in zip(clients, patients, strict=True)
        ]
    )

    won = [r for r in results if r.status_code == 201]
    assert len(won) == 12
    assert sorted(r.get_json()["token_number"] for r in won) == list(range(1, 13))
    assert {_code(r) for r in results if r.status_code != 201} == {"APT_SESSION_FULL"}
    assert _session(desk, world)["booked_count"] == 12
    _consistent(db)


def test_r20_a_booking_racing_a_schedule_change_is_never_lost(world: World, db: Engine) -> None:
    _schedule(world)
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = _session(desk, world)
    asha = _patient(desk)

    book, change = _in_parallel(
        [
            lambda: _book(desk, session["id"], asha),
            lambda: _send(
                owner,
                "PUT",
                f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule",
                {"blocks": []},
            ),
        ]
    )

    assert change.status_code == 200, change.get_json()
    status = _scalar(
        db, "SELECT coalesce(max(status), 'GONE') FROM sessions WHERE id = :id", id=session["id"]
    )
    if book.status_code == 201:
        # The booking won: the change found it and closed the session instead of deleting it.
        assert status == "CLOSED"
        assert [s["id"] for s in change.get_json()["kept_sessions"]] == [session["id"]]
    else:
        # The change won: the session is gone, and the booking says so.
        assert (book.status_code, _code(book)) == (404, "REQ_NOT_FOUND")
        assert status == "GONE"
    _consistent(db)


def test_two_crossing_reschedules_finish_without_deadlock(world: World, db: Engine) -> None:
    _schedule(world)
    desk, doctor = world.client_for(world.a.desk), world.client_for(world.a.doctor_user)
    monday, tuesday = _session(desk, world), _session(desk, world, TUESDAY)
    on_monday = _book(desk, monday["id"], _patient(desk)).get_json()["id"]
    on_tuesday = _book(desk, tuesday["id"], _patient(desk, "Bina Shah")).get_json()["id"]

    results = _in_parallel(
        [
            lambda: _send(
                desk,
                "POST",
                f"/api/v1/appointments/{on_monday}/reschedule",
                {"session_id": tuesday["id"]},
            ),
            lambda: _send(
                doctor,
                "POST",
                f"/api/v1/appointments/{on_tuesday}/reschedule",
                {"session_id": monday["id"]},
            ),
        ]
    )

    assert [r.status_code for r in results] == [201, 201], [r.get_json() for r in results]
    _consistent(db)


# --- Cancel (R7, D14) ----------------------------------------------------------------------------


def test_d14_cancel_rules(world: World) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    session = _session(desk, world)
    appointment = _book(desk, session["id"], _patient(desk)).get_json()["id"]
    url = f"/api/v1/appointments/{appointment}/cancel"

    no_note = _send(desk, "POST", url, {"reason": "OTHER"})
    assert (no_note.status_code, _code(no_note)) == (422, "REQ_VALIDATION_FAILED")
    rescheduled = _send(desk, "POST", url, {"reason": "RESCHEDULED"})
    assert rescheduled.status_code == 422
    done = _send(desk, "POST", url, {"reason": "OTHER", "note": "moved city"})
    assert done.status_code == 200
    assert done.get_json()["cancel_note"] == "moved city"
    twice = _send(desk, "POST", url, {"reason": "DUPLICATE"})
    assert (twice.status_code, _code(twice)) == (409, "APT_NOT_MODIFIABLE")
    assert twice.get_json()["error"]["details"] == {"status": "CANCELLED", "action": "cancelled"}


# --- Reschedule (R8, D15) ------------------------------------------------------------------------


def test_r8_d15_reschedule_moves_the_booking_and_keeps_the_history(
    world: World, db: Engine
) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    monday, tuesday = _session(desk, world), _session(desk, world, TUESDAY)
    asha = _patient(desk)
    old = _book(desk, monday["id"], asha, source="PHONE", reason="follow-up").get_json()

    same = _send(
        desk, "POST", f"/api/v1/appointments/{old['id']}/reschedule", {"session_id": monday["id"]}
    )
    assert (same.status_code, _code(same)) == (422, "REQ_VALIDATION_FAILED")

    moved = _send(
        desk, "POST", f"/api/v1/appointments/{old['id']}/reschedule", {"session_id": tuesday["id"]}
    )
    assert moved.status_code == 201, moved.get_json()
    new = moved.get_json()
    assert (new["rescheduled_from_id"], new["on_date"], new["token_number"]) == (
        old["id"],
        TUESDAY.isoformat(),
        1,
    )
    assert (new["source"], new["reason"], new["patient_id"]) == ("PHONE", "follow-up", asha)

    detail = desk.get(f"/api/v1/appointments/{old['id']}").get_json()
    assert (detail["status"], detail["cancel_reason"]) == ("CANCELLED", "RESCHEDULED")
    assert [(h["from_status"], h["to_status"]) for h in detail["history"]] == [
        (None, "BOOKED"),
        ("BOOKED", "CANCELLED"),
    ]
    assert _session(desk, world)["booked_count"] == 0
    assert _session(desk, world, TUESDAY)["booked_count"] == 1

    again = _send(
        desk, "POST", f"/api/v1/appointments/{old['id']}/reschedule", {"session_id": monday["id"]}
    )
    assert (again.status_code, _code(again)) == (409, "APT_NOT_MODIFIABLE")

    [row] = _audit(db, "appointment.rescheduled")
    assert (row["rescheduled_from_id"], row["from_session_id"]) == (old["id"], monday["id"])

    history = desk.get(f"/api/v1/patients/{asha}/appointments").get_json()["items"]
    assert [a["id"] for a in history] == [new["id"], old["id"]]
    _consistent(db)


# --- Schedule changes with bookings (D10, D11) ---------------------------------------------------


def test_d10_leave_closes_a_booked_session_and_bookings_can_leave_it(
    world: World, db: Engine
) -> None:
    _schedule(world)
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    monday, tuesday = _session(desk, world), _session(desk, world, TUESDAY)
    booked = _book(desk, monday["id"], _patient(desk)).get_json()

    leave = _send(
        owner,
        "POST",
        f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule-exceptions",
        {"kind": "LEAVE", "on_date": MONDAY.isoformat()},
    )
    assert leave.status_code == 201, leave.get_json()
    assert [s["id"] for s in leave.get_json()["kept_sessions"]] == [monday["id"]]
    assert leave.get_json()["kept_sessions"][0]["status"] == "CLOSED"

    closed = _session(desk, world)
    assert (closed["id"], closed["status"], closed["booked_count"]) == (monday["id"], "CLOSED", 1)
    refused = _book(desk, monday["id"], _patient(desk, "Bina Shah"))
    assert (refused.status_code, _code(refused)) == (409, "APT_SESSION_CLOSED")

    moved = _send(
        desk,
        "POST",
        f"/api/v1/appointments/{booked['id']}/reschedule",
        {"session_id": tuesday["id"]},
    )
    assert moved.status_code == 201, moved.get_json()
    # The leave day keeps the closed, now empty session for the cancelled appointment's history.
    assert _session(desk, world)["booked_count"] == 0

    # Removing the leave lets the day take bookings again.
    exception_id = leave.get_json()["exception"]["id"]
    removed = _send(
        owner,
        "DELETE",
        f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule-exceptions/{exception_id}",
    )
    assert removed.status_code == 200
    reopened = _session(desk, world)
    assert (reopened["id"], reopened["status"]) == (monday["id"], "OPEN")
    assert _book(desk, monday["id"], _patient(desk, "Chetan Iyer")).status_code == 201
    _consistent(db)


def test_d10_an_emptied_session_no_longer_planned_is_retired_then_revived(
    world: World, db: Engine
) -> None:
    _schedule(world)
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    monday = _session(desk, world)
    booked = _book(desk, monday["id"], _patient(desk)).get_json()
    assert (
        _send(
            desk, "POST", f"/api/v1/appointments/{booked['id']}/cancel", {"reason": "DUPLICATE"}
        ).status_code
        == 200
    )

    url = f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule"
    assert _send(owner, "PUT", url, {"blocks": []}).status_code == 200
    # Out of play but kept: the cancelled appointment still points at it.
    assert desk.get(f"/api/v1/sessions?date={MONDAY.isoformat()}").get_json()["items"] == []
    assert _scalar(db, "SELECT status FROM sessions WHERE id = :id", id=monday["id"]) == "CANCELLED"
    assert desk.get(f"/api/v1/appointments/{booked['id']}").status_code == 200

    _schedule(world)
    revived = _session(desk, world)
    assert (revived["id"], revived["status"], revived["next_token"]) == (monday["id"], "OPEN", 2)


def test_d11_a_capacity_only_change_resizes_a_booked_session(world: World) -> None:
    _schedule(world, capacity=2)
    desk = world.client_for(world.a.desk)
    monday = _session(desk, world)
    for name in ("Asha Rao", "Bina Shah"):
        assert _book(desk, monday["id"], _patient(desk, name)).status_code == 201

    _schedule(world, capacity=5)

    resized = _session(desk, world)
    assert (resized["id"], resized["capacity"], resized["available"], resized["status"]) == (
        monday["id"],
        5,
        3,
        "OPEN",
    )
    assert _book(desk, monday["id"], _patient(desk, "Chetan Iyer")).status_code == 201

    _schedule(world, capacity=2)  # below the three bookings: closed instead (D11)
    assert _session(desk, world)["status"] == "CLOSED"


# --- Reads and tenancy ---------------------------------------------------------------------------


def test_fr_apt_05_one_appointment_and_a_patients_list(world: World) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    asha = _patient(desk)
    booked = _book(desk, _session(desk, world)["id"], asha).get_json()

    detail = desk.get(f"/api/v1/appointments/{booked['id']}")
    assert detail.status_code == 200
    assert detail.get_json()["history"][0]["to_status"] == "BOOKED"
    assert detail.headers["Cache-Control"] == "no-store"
    listed = desk.get(f"/api/v1/patients/{asha}/appointments").get_json()["items"]
    assert [a["id"] for a in listed] == [booked["id"]]
    assert (
        desk.get(f"/api/v1/patients/{_patient(desk, 'Nobody Yet')}/appointments").get_json()[
            "items"
        ]
        == []
    )
    unknown = desk.get("/api/v1/appointments/01a00000-0000-7000-8000-000000000000")
    assert (unknown.status_code, _code(unknown)) == (404, "REQ_NOT_FOUND")


def test_nfr_08_another_clinics_patient_or_session_cannot_be_booked(world: World) -> None:
    _schedule(world)
    owner_a, owner_b = world.client_for(world.a.owner), world.client_for(world.b.owner)
    session_a = _session(owner_a, world)
    patient_b = _patient(owner_b)

    stranger = _book(owner_a, session_a["id"], patient_b)
    assert (stranger.status_code, stranger.get_json()["error"]["details"]) == (
        404,
        {"entity": "patient"},
    )
    elsewhere = _book(owner_b, session_a["id"], patient_b)
    assert (elsewhere.status_code, elsewhere.get_json()["error"]["details"]) == (
        404,
        {"entity": "session"},
    )
