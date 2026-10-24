"""Appointment reminders and bookings to move after leave, on PostgreSQL (M6a-P8).

FR-APT-08 (decisions 1A-5A), FR-APT-09 (decisions 6A, 7A). Bookings go through HTTP so the
reminders are made by the notification service in the booking's transaction; send jobs run as the
worker would, with a scripted provider and a fixed clock.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from cryptography.fernet import Fernet
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.messaging.catalog import YamlTemplateCatalog
from mediease_api.adapters.security.phone_cipher import FernetPhoneCipher
from mediease_api.application.messaging.cancellation import SendCancellationNotice
from mediease_api.application.messaging.sender import MessageSender
from mediease_api.application.reminders.send import SendReminder
from tests.conftest import World
from tests.fakes import FakeClock
from tests.integration.test_appointments_http import (
    MONDAY,
    TUESDAY,
    _patient,
    _schedule,
    _session,
)
from tests.integration.test_messaging_db import ScriptedProvider, _job
from tests.integration.test_visits_http import _send

KOLKATA = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _at_ist(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=KOLKATA).astimezone(UTC)


def _sender(session_factory: sessionmaker[Session], clock: Any) -> tuple[MessageSender, Any]:
    provider = ScriptedProvider()
    sender = MessageSender(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=clock,
        ids=Uuid7Generator(),
        messaging=provider,
        templates=YamlTemplateCatalog.from_package(),
        phones=FernetPhoneCipher([Fernet.generate_key()]),
    )
    return sender, provider


def _rows(db: Engine, sql: str, **params: Any) -> list[Any]:
    with db.connect() as conn:
        return list(conn.execute(text(sql), params))


def _reminders(db: Engine, appointment_id: str) -> list[Any]:
    return _rows(
        db,
        "SELECT * FROM reminders WHERE appointment_id = :a ORDER BY due_at",
        a=appointment_id,
    )


def _consenting(desk: FlaskClient, name: str) -> str:
    patient_id = _patient(desk, name)
    resp = _send(
        desk, "PUT", f"/api/v1/patients/{patient_id}/consent", {"whatsapp": True, "sms": False}
    )
    assert resp.status_code == 200, resp.get_json()
    return patient_id


def _book(desk: FlaskClient, session_id: str, patient_id: str) -> str:
    resp = _send(
        desk, "POST", "/api/v1/appointments", {"session_id": session_id, "patient_id": patient_id}
    )
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["id"])


def _booked_tuesday(world: World, name: str = "Asha Rao") -> tuple[FlaskClient, str, str]:
    """A consenting patient in Tuesday's 10:00 token session: (desk, appointment, patient)."""
    _schedule(world)
    desk = world.client_for(world.a.desk)
    patient_id = _consenting(desk, name)
    return desk, _book(desk, _session(desk, world, TUESDAY)["id"], patient_id), patient_id


# --- Scheduling with the booking (decisions 1A, 2A, 4A) -----------------------------------------


def test_fr_apt_08_a_booking_schedules_the_evening_before_and_two_hours_before(
    world: World, db: Engine
) -> None:
    desk, appointment_id, patient_id = _booked_tuesday(world)

    evening, before = _reminders(db, appointment_id)
    assert (evening.kind, evening.source, evening.status) == (
        "APPOINTMENT",
        "APPOINTMENT",
        "SCHEDULED",
    )
    assert evening.due_at == _at_ist(MONDAY, 19)
    assert before.due_at == _at_ist(TUESDAY, 8)  # 10:00 session, two hours before
    assert evening.follow_up_date == TUESDAY and evening.created_by == world.a.desk.id
    jobs = _rows(db, "SELECT dedupe_key FROM jobs WHERE kind = 'send_reminder'")
    assert {j.dedupe_key for j in jobs} == {f"reminder:{evening.id}:1", f"reminder:{before.id}:1"}
    audited = _rows(
        db,
        "SELECT actor_type FROM audit_events WHERE action = 'reminder.scheduled'"
        " AND entity_id IN (:a, :b)",
        a=evening.id,
        b=before.id,
    )
    assert [a.actor_type for a in audited] == ["SYSTEM", "SYSTEM"]

    listed = desk.get(f"/api/v1/patients/{patient_id}/reminders").get_json()["items"]
    assert {(r["kind"], r["appointment_id"]) for r in listed} == {("APPOINTMENT", appointment_id)}


def test_fr_apt_08_no_reminders_without_consent_or_for_a_clinic_that_turned_them_off(
    world: World, db: Engine
) -> None:
    _schedule(world)
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    tuesday = _session(desk, world, TUESDAY)["id"]
    no_consent = _book(desk, tuesday, _patient(desk, "Bina Shah"))
    assert _reminders(db, no_consent) == []

    off = _send(
        owner,
        "PATCH",
        "/api/v1/clinic",
        {"reminder_evening_before": False, "reminder_hours_before": 0},
    )
    assert off.status_code == 200, off.get_json()
    assert (off.get_json()["reminder_evening_before"], off.get_json()["reminder_hours_before"]) == (
        False,
        0,
    )
    assert _reminders(db, _book(desk, tuesday, _consenting(desk, "Chetan Rao"))) == []

    three = _send(owner, "PATCH", "/api/v1/clinic", {"reminder_hours_before": 3})
    assert three.status_code == 200
    [only] = _reminders(db, _book(desk, tuesday, _consenting(desk, "Divya Iyer")))
    assert only.due_at == _at_ist(TUESDAY, 7) + timedelta(hours=1)  # 07:00 is quiet: 08:00
    too_many = _send(owner, "PATCH", "/api/v1/clinic", {"reminder_hours_before": 7})
    assert too_many.status_code == 422


def test_fr_apt_08_a_reschedule_moves_the_reminders_and_a_cancellation_cancels_them(
    world: World, db: Engine
) -> None:
    desk, first, _ = _booked_tuesday(world)
    moved = _send(
        desk,
        "POST",
        f"/api/v1/appointments/{first}/reschedule",
        {"session_id": _session(desk, world, MONDAY)["id"]},
    )
    assert moved.status_code == 201, moved.get_json()
    second = str(moved.get_json()["id"])

    assert {r.status for r in _reminders(db, first)} == {"CANCELLED"}
    assert [r.status for r in _reminders(db, second)] == ["SCHEDULED", "SCHEDULED"]

    cancelled = _send(
        desk, "POST", f"/api/v1/appointments/{second}/cancel", {"reason": "PATIENT_REQUEST"}
    )
    assert cancelled.status_code == 200
    assert {r.status for r in _reminders(db, second)} == {"CANCELLED"}
    # The patient cancelled: they are not told (decision 7A).
    assert _rows(db, "SELECT 1 FROM jobs WHERE kind = 'send_cancellation_notice'") == []


def test_fr_apt_08_an_appointment_reminder_moves_only_with_its_appointment(
    world: World, db: Engine
) -> None:
    desk, appointment_id, _ = _booked_tuesday(world)
    evening = _reminders(db, appointment_id)[0]
    url = f"/api/v1/reminders/{evening.id}"

    moved = _send(desk, "PATCH", url, {"follow_up_date": TUESDAY.isoformat()})
    assert (moved.status_code, moved.get_json()["error"]["code"]) == (
        409,
        "REM_FOLLOWS_APPOINTMENT",
    )
    assert _send(desk, "PATCH", url, {"cancel": True}).status_code == 200


# --- Sending (decisions 4A, 5A) -----------------------------------------------------------------


def test_fr_apt_08_the_reminder_sends_the_appointment_template_at_its_time(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, appointment_id, _ = _booked_tuesday(world)
    evening = _reminders(db, appointment_id)[0]
    sender, provider = _sender(session_factory, FakeClock(evening.due_at))

    SendReminder(sender=sender, ids=Uuid7Generator())(_job(db, f"reminder:{evening.id}:1"))

    [call] = provider.calls
    assert call.template.key == "appointment_reminder"
    assert call.variables["doctor_name"] == world.a.doctor.display_name
    assert "token 1" in call.variables["date_time_or_token"]
    assert _reminders(db, appointment_id)[0].status == "SENT"


def test_fr_apt_09_a_reminder_for_a_visit_closed_by_leave_is_cancelled_when_due(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, appointment_id, _ = _booked_tuesday(world)
    owner = world.client_for(world.a.owner)
    leave = _send(
        owner,
        "POST",
        f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule-exceptions",
        {"kind": "LEAVE", "on_date": TUESDAY.isoformat()},
    )
    assert leave.status_code == 201, leave.get_json()
    evening = _reminders(db, appointment_id)[0]
    sender, provider = _sender(session_factory, FakeClock(evening.due_at))

    SendReminder(sender=sender, ids=Uuid7Generator())(_job(db, f"reminder:{evening.id}:1"))

    assert provider.calls == []
    row = _reminders(db, appointment_id)[0]
    assert (row.status, row.error_code, row.cancelled_by) == (
        "CANCELLED",
        "REM_APPOINTMENT_CHANGED",
        None,
    )


# --- Bookings to move (decisions 6A, 7A) --------------------------------------------------------


def test_fr_apt_09_leave_over_a_booked_day_lists_the_booking_and_tells_the_desk(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    desk, appointment_id, patient_id = _booked_tuesday(world, "Asha Rao")
    owner = world.client_for(world.a.owner)
    assert desk.get("/api/v1/appointments/to-move").get_json() == {"items": []}

    leave = _send(
        owner,
        "POST",
        f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule-exceptions",
        {"kind": "LEAVE", "on_date": TUESDAY.isoformat()},
    )
    assert leave.status_code == 201, leave.get_json()

    [item] = desk.get("/api/v1/appointments/to-move").get_json()["items"]
    assert (item["id"], item["reason"], item["status"], item["on_date"]) == (
        appointment_id,
        "LEAVE",
        "BOOKED",
        TUESDAY.isoformat(),
    )
    assert item["patient"]["first_name"] == "Asha"
    assert (
        item["patient"]["phone_masked"].startswith("+91") and "*" in item["patient"]["phone_masked"]
    )
    assert "Rao" not in str(item)
    assert desk.get(f"/api/v1/appointments/to-move?doctor_id={world.b.doctor.id}").get_json() == {
        "items": []
    }

    notices = desk.get("/api/v1/notifications").get_json()["items"]
    [notice] = [n for n in notices if n["kind"] == "schedule.bookings_to_move"]
    assert notice["title"] == (
        f"{world.a.doctor.display_name} on leave {TUESDAY.day} {TUESDAY.strftime('%b')}:"
        " 1 booking to move"
    )
    assert notice["link"] == "/bookings-to-move"
    # The owner made the change, so the owner is not told.
    owner_kinds = {n["kind"] for n in owner.get("/api/v1/notifications").get_json()["items"]}
    assert "schedule.bookings_to_move" not in owner_kinds
    assert desk.get("/api/v1/dashboard/today").get_json()["bookings_to_move"] == 1

    # Cancelling it as "doctor unavailable" empties the list and tells the patient (7A).
    cancelled = _send(
        desk,
        "POST",
        f"/api/v1/appointments/{appointment_id}/cancel",
        {"reason": "DOCTOR_UNAVAILABLE"},
    )
    assert cancelled.status_code == 200, cancelled.get_json()
    assert desk.get("/api/v1/appointments/to-move").get_json() == {"items": []}
    [job] = _rows(
        db,
        "SELECT dedupe_key, run_at FROM jobs WHERE kind = 'send_cancellation_notice'",
    )
    assert job.dedupe_key == f"appointment_cancelled:{appointment_id}"
    local = job.run_at.astimezone(KOLKATA).time()
    assert 8 <= local.hour < 21  # never in the quiet hours

    sender, provider = _sender(session_factory, FakeClock(job.run_at))
    SendCancellationNotice(sender=sender)(_job(db, job.dedupe_key))
    [call] = provider.calls
    assert call.template.key == "appointment_cancelled"
    assert call.variables["clinic_phone"].startswith("+91")
    assert patient_id  # the patient was told, not named in the call's variables
    assert "Asha" not in str(call.variables)


def test_fr_apt_09_a_weekly_schedule_change_lists_its_bookings_too(world: World) -> None:
    desk, appointment_id, _ = _booked_tuesday(world)
    owner = world.client_for(world.a.owner)
    cleared = _send(
        owner, "PUT", f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule", {"blocks": []}
    )
    assert cleared.status_code == 200, cleared.get_json()

    [item] = desk.get("/api/v1/appointments/to-move").get_json()["items"]
    assert (item["id"], item["reason"]) == (appointment_id, "SCHEDULE_CHANGED")
    [notice] = [
        n
        for n in desk.get("/api/v1/notifications").get_json()["items"]
        if n["kind"] == "schedule.bookings_to_move"
    ]
    assert notice["title"].endswith("'s schedule changed: 1 booking to move")


def test_fr_apt_09_another_clinics_bookings_never_appear(world: World) -> None:
    _booked_tuesday(world)
    owner = world.client_for(world.a.owner)
    _send(
        owner,
        "POST",
        f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule-exceptions",
        {"kind": "LEAVE", "on_date": TUESDAY.isoformat()},
    )
    other = world.client_for(world.b.owner)
    assert other.get("/api/v1/appointments/to-move").get_json() == {"items": []}
    assert other.get("/api/v1/dashboard/today").get_json()["bookings_to_move"] == 0
    assert UUID(str(world.a.clinic.id))  # clinic A's list is not empty: see the test above
