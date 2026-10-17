"""Schedules, exceptions and sessions over HTTP on PostgreSQL (M3-P1; spec R1-R4, R14-R20; AC5).

Dates are computed from the clinic's today (Asia/Kolkata), because the app runs on the system
clock: every test works on a Monday at least a week ahead, well inside the 180-day horizon.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from tests.conftest import World

KOLKATA = ZoneInfo("Asia/Kolkata")


def _today() -> date:
    return datetime.now(KOLKATA).date()


def _next_monday() -> date:
    today = _today()
    return today + timedelta(days=7 + (7 - today.weekday()) % 7)


MONDAY = _next_monday()
SUNDAY = MONDAY - timedelta(days=1)


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _send(client: FlaskClient, method: str, url: str, body: Any = None) -> TestResponse:
    csrf = client.get_cookie("me_csrf", path="/")
    headers = {"X-CSRF-Token": csrf.value} if csrf is not None else {}
    return client.open(url, method=method, json=body, headers=headers)


def _schedule_url(world: World, *, clinic: str = "a") -> str:
    doctor = (world.a if clinic == "a" else world.b).doctor
    return f"/api/v1/clinic/doctors/{doctor.id}/schedule"


def _exceptions_url(world: World) -> str:
    return f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule-exceptions"


def _sessions(client: FlaskClient, on: date, doctor_id: object = None) -> TestResponse:
    query = f"date={on.isoformat()}" + (f"&doctor_id={doctor_id}" if doctor_id else "")
    return client.get(f"/api/v1/sessions?{query}")


def _block(weekday: int, start: str, end: str, **extra: object) -> dict[str, object]:
    return {"weekday": weekday, "start_time": start, "end_time": end, **extra}


def _book(db: Engine, session_id: str, count: int = 1) -> None:
    """Stands in for a P2 booking: the session now has someone booked."""
    with db.begin() as conn:
        conn.execute(
            text("UPDATE sessions SET booked_count = :n WHERE id = :id"),
            {"n": count, "id": session_id},
        )


def _audit(db: Engine, action: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT actor_type, metadata FROM audit_events WHERE action = :a"
                " ORDER BY occurred_at"
            ),
            {"a": action},
        ).all()
    return [{"actor_type": r[0], "metadata": r[1]} for r in rows]


# --- Weekly schedule and lazy generation (FR-APT-01, R1, R16) ------------------------------------


def test_fr_apt_01_r1_a_schedule_generates_the_dates_sessions_once(
    world: World, db: Engine
) -> None:
    owner = world.client_for(world.a.owner)

    put = _send(
        owner, "PUT", _schedule_url(world), {"blocks": [_block(0, "10:00", "13:00", capacity=12)]}
    )
    assert put.status_code == 200, put.get_json()
    body = put.get_json()
    assert body["booking_mode"] == "TOKENS"
    assert [
        (b["weekday"], b["start_time"], b["end_time"], b["overnight"]) for b in body["blocks"]
    ] == [(0, "10:00", "13:00", False)]
    assert body["kept_sessions"] == []

    first = _sessions(owner, MONDAY, world.a.doctor.id)
    assert first.status_code == 200
    [session] = first.get_json()["items"]
    assert session["on_date"] == MONDAY.isoformat()
    assert session["starts_at"] == f"{MONDAY.isoformat()}T04:30:00+00:00"
    assert (session["mode"], session["capacity"], session["available"], session["next_token"]) == (
        "TOKENS",
        12,
        12,
        1,
    )
    assert session["slots"] == []
    # Reading again generates nothing new: the same session, by ID.
    assert [s["id"] for s in _sessions(owner, MONDAY).get_json()["items"]] == [session["id"]]
    assert _sessions(owner, MONDAY + timedelta(days=1)).get_json()["items"] == []

    [changed] = _audit(db, "schedule.changed")
    assert changed["actor_type"] == "STAFF"
    assert changed["metadata"] == {"blocks": "1", "kept_sessions": "0"}

    schedule = owner.get(_schedule_url(world))
    assert schedule.status_code == 200
    assert len(schedule.get_json()["blocks"]) == 1


def test_r1_two_screens_reading_one_new_date_create_one_set(world: World, db: Engine) -> None:
    owner = world.client_for(world.a.owner)
    assert (
        _send(
            owner,
            "PUT",
            _schedule_url(world),
            {
                "blocks": [
                    _block(0, "10:00", "13:00", capacity=12),
                    _block(0, "15:00", "17:00", capacity=8),
                ]
            },
        ).status_code
        == 200
    )
    clients = [world.client_for(world.a.desk), world.client_for(world.a.doctor_user)]
    barrier = threading.Barrier(len(clients), timeout=10)
    statuses: list[int] = []

    def read(client: FlaskClient) -> None:
        barrier.wait()
        statuses.append(_sessions(client, MONDAY).status_code)

    threads = [threading.Thread(target=read, args=(c,)) for c in clients]
    for thread in threads:  # start every thread before any of them waits (DEBUG_JOURNAL)
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert statuses == [200, 200]
    with db.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM sessions WHERE on_date = :d"), {"d": MONDAY}
        ).scalar_one()
    assert count == 2


def test_ac5_r2_an_overnight_slot_session_belongs_to_its_start_date(world: World) -> None:
    owner = world.client_for(world.a.owner)
    assert _send(owner, "PATCH", "/api/v1/clinic", {"booking_mode": "SLOTS"}).status_code == 200

    put = _send(
        owner,
        "PUT",
        _schedule_url(world),
        {"blocks": [_block(0, "23:00", "01:00", slot_minutes=30)]},
    )
    assert put.status_code == 200, put.get_json()
    assert put.get_json()["blocks"][0]["overnight"] is True

    [session] = _sessions(owner, MONDAY).get_json()["items"]
    assert session["on_date"] == MONDAY.isoformat()
    assert session["starts_at"] == f"{MONDAY.isoformat()}T17:30:00+00:00"
    assert session["ends_at"] == f"{MONDAY.isoformat()}T19:30:00+00:00"
    assert (session["mode"], session["capacity"], session["next_token"]) == ("SLOTS", 4, None)
    assert [s["starts_at"][11:16] for s in session["slots"]] == ["17:30", "18:00", "18:30", "19:00"]
    assert _sessions(owner, MONDAY + timedelta(days=1)).get_json()["items"] == []


# --- Refusals (R14, R15) -------------------------------------------------------------------------


def test_r14_a_daytime_inversion_is_refused_and_a_night_shift_accepted(world: World) -> None:
    owner = world.client_for(world.a.owner)

    inverted = _send(
        owner, "PUT", _schedule_url(world), {"blocks": [_block(2, "13:00", "10:00", capacity=5)]}
    )
    assert inverted.status_code == 422
    error = inverted.get_json()["error"]
    assert error["code"] == "SCH_INVALID_BLOCK"
    assert error["details"]["index"] == "0"
    assert "12 hours" in error["details"]["reason"]

    night = _send(
        owner, "PUT", _schedule_url(world), {"blocks": [_block(2, "23:00", "01:00", capacity=5)]}
    )
    assert night.status_code == 200
    # The mode's value is required: token mode needs a capacity.
    missing = _send(owner, "PUT", _schedule_url(world), {"blocks": [_block(2, "10:00", "11:00")]})
    assert missing.get_json()["error"]["code"] == "SCH_INVALID_BLOCK"


def test_r15_d7_an_overnight_block_cannot_spill_into_the_next_mornings_block(world: World) -> None:
    owner = world.client_for(world.a.owner)
    blocks = [_block(6, "22:00", "02:00", capacity=5), _block(0, "01:00", "05:00", capacity=5)]

    resp = _send(owner, "PUT", _schedule_url(world), {"blocks": blocks})

    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "SCH_OVERLAP"
    assert resp.get_json()["error"]["details"] == {"first": "0", "second": "1"}
    # Nothing changed: the refused schedule left no blocks behind.
    assert owner.get(_schedule_url(world)).get_json()["blocks"] == []


def test_validation_failures_are_field_errors(world: World) -> None:
    owner = world.client_for(world.a.owner)
    bad = _send(
        owner, "PUT", _schedule_url(world), {"blocks": [_block(7, "10:00", "11:00", capacity=1)]}
    )
    assert bad.status_code == 422 and bad.get_json()["error"]["code"] == "REQ_VALIDATION_FAILED"
    assert owner.get("/api/v1/sessions").status_code == 422
    assert owner.get("/api/v1/sessions?date=tomorrow").status_code == 422
    assert owner.get(f"/api/v1/sessions?date={MONDAY}&doctor_id=nope").status_code == 422
    too_far = _sessions(owner, _today() + timedelta(days=181))
    assert too_far.status_code == 422
    assert too_far.get_json()["error"]["details"]["fields"][0]["field"] == "date"


# --- Changes never drop a booking (D4, R16, R17, R18) --------------------------------------------


def test_r16_d4_replacing_a_schedule_keeps_booked_sessions_and_returns_them(
    world: World, db: Engine
) -> None:
    owner = world.client_for(world.a.owner)
    _send(
        owner,
        "PUT",
        _schedule_url(world),
        {
            "blocks": [
                _block(0, "10:00", "13:00", capacity=12),
                _block(0, "15:00", "17:00", capacity=8),
            ]
        },
    )
    morning, afternoon = _sessions(owner, MONDAY).get_json()["items"]
    _book(db, afternoon["id"])

    put = _send(
        owner, "PUT", _schedule_url(world), {"blocks": [_block(0, "09:00", "12:00", capacity=10)]}
    )

    assert put.status_code == 200
    assert [s["id"] for s in put.get_json()["kept_sessions"]] == [afternoon["id"]]
    items = _sessions(owner, MONDAY).get_json()["items"]
    starts = [s["starts_at"][11:16] for s in items]
    assert starts == ["03:30", "09:30"]  # the new 09:00 IST block, and the booked 15:00 kept
    assert morning["id"] not in {s["id"] for s in items}
    assert _audit(db, "schedule.changed")[-1]["metadata"]["kept_sessions"] == "1"


def test_r17_leave_on_a_generated_date_removes_unbooked_and_keeps_booked_sessions(
    world: World, db: Engine
) -> None:
    owner = world.client_for(world.a.owner)
    _send(
        owner,
        "PUT",
        _schedule_url(world),
        {
            "blocks": [
                _block(0, "10:00", "13:00", capacity=12),
                _block(0, "15:00", "17:00", capacity=8),
            ]
        },
    )
    morning, afternoon = _sessions(owner, MONDAY).get_json()["items"]
    _book(db, afternoon["id"], count=3)

    leave = _send(
        owner,
        "POST",
        _exceptions_url(world),
        {"kind": "LEAVE", "on_date": MONDAY.isoformat(), "note": "Conference"},
    )

    assert leave.status_code == 201, leave.get_json()
    body = leave.get_json()
    assert body["exception"]["kind"] == "LEAVE" and body["exception"]["start_time"] is None
    assert [(s["id"], s["booked_count"]) for s in body["kept_sessions"]] == [(afternoon["id"], 3)]
    assert [s["id"] for s in _sessions(owner, MONDAY).get_json()["items"]] == [afternoon["id"]]
    [added] = _audit(db, "schedule.exception_added")
    assert added["metadata"]["kind"] == "LEAVE" and added["metadata"]["kept_sessions"] == "1"
    assert "Conference" not in str(added["metadata"])

    again = _send(
        owner, "POST", _exceptions_url(world), {"kind": "LEAVE", "on_date": MONDAY.isoformat()}
    )
    assert again.status_code == 409 and again.get_json()["error"]["code"] == "SCH_LEAVE_EXISTS"

    removed = _send(owner, "DELETE", f"{_exceptions_url(world)}/{body['exception']['id']}")
    assert removed.status_code == 200 and removed.get_json()["kept_sessions"] == []
    regenerated = _sessions(owner, MONDAY).get_json()["items"]
    assert len(regenerated) == 2 and afternoon["id"] in {s["id"] for s in regenerated}
    assert morning["id"] not in {s["id"] for s in regenerated}  # the morning came back as new


def test_r18_an_extra_session_is_added_and_removed(world: World, db: Engine) -> None:
    owner = world.client_for(world.a.owner)
    extra = _send(
        owner,
        "POST",
        _exceptions_url(world),
        {
            "kind": "EXTRA",
            "on_date": MONDAY.isoformat(),
            "start_time": "18:00",
            "end_time": "19:00",
            "capacity": 6,
        },
    )
    assert extra.status_code == 201
    [session] = _sessions(owner, MONDAY).get_json()["items"]
    assert session["capacity"] == 6
    assert owner.get(_schedule_url(world)).get_json()["exceptions"][0]["kind"] == "EXTRA"

    _book(db, session["id"])
    removed = _send(
        owner, "DELETE", f"{_exceptions_url(world)}/{extra.get_json()['exception']['id']}"
    )
    assert [s["id"] for s in removed.get_json()["kept_sessions"]] == [session["id"]]
    assert _audit(db, "schedule.exception_removed")[0]["metadata"]["kind"] == "EXTRA"


def test_r15_an_extra_cannot_overlap_the_previous_nights_block(world: World) -> None:
    owner = world.client_for(world.a.owner)
    _send(owner, "PUT", _schedule_url(world), {"blocks": [_block(6, "22:00", "02:00", capacity=5)]})

    clash = _send(
        owner,
        "POST",
        _exceptions_url(world),
        {
            "kind": "EXTRA",
            "on_date": MONDAY.isoformat(),
            "start_time": "01:00",
            "end_time": "03:00",
            "capacity": 4,
        },
    )
    assert clash.status_code == 409 and clash.get_json()["error"]["code"] == "SCH_OVERLAP"

    after = _send(
        owner,
        "POST",
        _exceptions_url(world),
        {
            "kind": "EXTRA",
            "on_date": MONDAY.isoformat(),
            "start_time": "02:00",
            "end_time": "04:00",
            "capacity": 4,
        },
    )
    assert after.status_code == 201
    # An extra running past midnight into the next day's block clashes too.
    tomorrow_block = _send(
        owner,
        "PUT",
        _schedule_url(world),
        {
            "blocks": [
                _block(6, "22:00", "02:00", capacity=5),
                _block(1, "00:30", "03:00", capacity=5),
            ]
        },
    )
    assert tomorrow_block.status_code == 200
    late = _send(
        owner,
        "POST",
        _exceptions_url(world),
        {
            "kind": "EXTRA",
            "on_date": MONDAY.isoformat(),
            "start_time": "23:00",
            "end_time": "01:00",
            "capacity": 4,
        },
    )
    assert late.status_code == 409


def test_exception_dates_and_shapes_are_checked(world: World, db: Engine) -> None:
    owner = world.client_for(world.a.owner)
    url = _exceptions_url(world)
    past = _send(
        owner, "POST", url, {"kind": "LEAVE", "on_date": (_today() - timedelta(days=1)).isoformat()}
    )
    assert past.status_code == 422
    leave_with_times = _send(
        owner, "POST", url, {"kind": "LEAVE", "on_date": MONDAY.isoformat(), "start_time": "10:00"}
    )
    assert leave_with_times.status_code == 422
    extra_without_end = _send(
        owner, "POST", url, {"kind": "EXTRA", "on_date": MONDAY.isoformat(), "start_time": "10:00"}
    )
    assert extra_without_end.status_code == 422
    assert _send(owner, "DELETE", f"{url}/00000000-0000-0000-0000-000000000001").status_code == 404

    # A past exception is history: inserted directly, it cannot be removed.
    with db.begin() as conn:
        exception_id = conn.execute(
            text(
                "INSERT INTO schedule_exceptions (id, clinic_id, doctor_id, on_date, kind,"
                " created_at, updated_at) VALUES (gen_random_uuid(), :c, :d, :on, 'LEAVE',"
                " now(), now()) RETURNING id"
            ),
            {"c": world.a.clinic.id, "d": world.a.doctor.id, "on": _today() - timedelta(days=3)},
        ).scalar_one()
    old = _send(owner, "DELETE", f"{url}/{exception_id}")
    assert old.status_code == 422


# --- Booking mode (R19) and inactive doctors ---------------------------------------------


def test_r19_the_mode_cannot_change_while_a_block_lacks_what_it_needs(world: World) -> None:
    owner = world.client_for(world.a.owner)
    _send(
        owner, "PUT", _schedule_url(world), {"blocks": [_block(0, "10:00", "13:00", capacity=12)]}
    )
    assert _sessions(owner, MONDAY).get_json()["items"][0]["mode"] == "TOKENS"

    refused = _send(owner, "PATCH", "/api/v1/clinic", {"booking_mode": "SLOTS"})
    assert refused.status_code == 409
    assert refused.get_json()["error"]["code"] == "SCH_MODE_INCOMPATIBLE"
    assert owner.get("/api/v1/clinic").get_json()["booking_mode"] == "TOKENS"

    _send(
        owner,
        "PUT",
        _schedule_url(world),
        {"blocks": [_block(0, "10:00", "13:00", capacity=12, slot_minutes=15)]},
    )
    changed = _send(owner, "PATCH", "/api/v1/clinic", {"booking_mode": "SLOTS"})
    assert changed.status_code == 200 and changed.get_json()["booking_mode"] == "SLOTS"
    [session] = _sessions(owner, MONDAY).get_json()["items"]
    assert (session["mode"], session["capacity"], len(session["slots"])) == ("SLOTS", 12, 12)


def test_an_inactive_doctor_gets_no_new_sessions(world: World) -> None:
    owner = world.client_for(world.a.owner)
    _send(
        owner, "PUT", _schedule_url(world), {"blocks": [_block(0, "10:00", "13:00", capacity=12)]}
    )
    assert (
        _send(
            owner, "PATCH", f"/api/v1/clinic/doctors/{world.a.doctor.id}", {"is_active": False}
        ).status_code
        == 200
    )

    assert _sessions(owner, MONDAY, world.a.doctor.id).get_json()["items"] == []
    assert _sessions(owner, MONDAY).get_json()["items"] == []


def test_a_past_date_shows_what_exists_and_generates_nothing(world: World) -> None:
    owner = world.client_for(world.a.owner)
    _send(
        owner,
        "PUT",
        _schedule_url(world),
        {"blocks": [_block(d, "10:00", "11:00", capacity=3) for d in range(7)]},
    )
    assert _sessions(owner, _today() - timedelta(days=1)).get_json()["items"] == []


# --- Who may do what (D5) and tenancy (NFR-08) ---------------------------------------------------


@pytest.mark.parametrize("role", ["desk", "doctor_user"])
def test_d5_only_the_owner_edits_schedules_while_every_role_reads(world: World, role: str) -> None:
    client = world.client_for(getattr(world.a, role))
    put = _send(client, "PUT", _schedule_url(world), {"blocks": []})
    assert put.status_code == 403 and put.get_json()["error"]["code"] == "PERM_DENIED"
    leave = _send(
        client, "POST", _exceptions_url(world), {"kind": "LEAVE", "on_date": MONDAY.isoformat()}
    )
    assert leave.status_code == 403
    assert client.get(_schedule_url(world)).status_code == 200
    assert _sessions(client, MONDAY).status_code == 200


def test_d5_ops_set_a_schedule_during_onboarding_through_their_own_route(
    world: World, db: Engine
) -> None:
    ops = world.client_for(world.ops)
    url = f"/api/v1/ops/clinics/{world.a.clinic.id}/doctors/{world.a.doctor.id}/schedule"

    resp = _send(ops, "PUT", url, {"blocks": [_block(0, "10:00", "13:00", capacity=12)]})

    assert resp.status_code == 200
    assert _audit(db, "schedule.changed")[0]["actor_type"] == "OPS"
    assert _send(ops, "PUT", _schedule_url(world), {"blocks": []}).status_code == 403
    other = f"/api/v1/ops/clinics/{world.a.clinic.id}/doctors/{world.b.doctor.id}/schedule"
    assert _send(ops, "PUT", other, {"blocks": []}).status_code == 404
    owner = world.client_for(world.a.owner)
    assert _send(owner, "PUT", url, {"blocks": []}).status_code == 403


def test_nfr_08_another_clinics_doctor_schedule_and_sessions_are_404_or_absent(
    world: World,
) -> None:
    owner_b = world.client_for(world.b.owner)
    _send(
        owner_b,
        "PUT",
        _schedule_url(world, clinic="b"),
        {"blocks": [_block(0, "10:00", "13:00", capacity=12)]},
    )
    assert len(_sessions(owner_b, MONDAY).get_json()["items"]) == 1

    owner_a = world.client_for(world.a.owner)
    assert (
        _send(owner_a, "PUT", _schedule_url(world, clinic="b"), {"blocks": []}).status_code == 404
    )
    other = _sessions(owner_a, MONDAY, world.b.doctor.id)
    assert other.status_code == 404 and other.get_json()["error"]["code"] == "REQ_NOT_FOUND"
    assert _sessions(owner_a, MONDAY).get_json()["items"] == []
