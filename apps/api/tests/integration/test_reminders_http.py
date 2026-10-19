"""Reminders, pending follow-ups and the automatic no-show on PostgreSQL (M5-P4).

FR-REM-01, 02, 04, 05, 07; spec R1-R5, R17, AC1, AC2; appointments R10; decisions 1A-6A.
Prescriptions are issued over HTTP so the reminder is made by the real use case; send jobs run as
the worker would, with a scripted provider and a fixed clock.
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
from mediease_api.application.appointments.no_show import MarkNoShows, SweepNoShows
from mediease_api.application.messaging.sender import MessageSender
from mediease_api.application.reminders.send import SendReminder
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.prescriptions.prescription import Advice, Prescription, PrescriptionItem
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession
from mediease_api.domain.scheduling.sessions import Session as ClinicSession
from tests.builders import new_id
from tests.conftest import UowFactory, World
from tests.fakes import FakeClock
from tests.integration.test_messaging_db import ScriptedProvider, _job
from tests.integration.test_prescriptions_http import _draft, _fill
from tests.integration.test_visits_http import _past_visit, _send

KOLKATA = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _today() -> date:
    return datetime.now(KOLKATA).date()


def _at_ist(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=KOLKATA).astimezone(UTC)


def _sender(
    session_factory: sessionmaker[Session], clock: Any
) -> tuple[SendReminder, ScriptedProvider]:
    provider = ScriptedProvider()
    sender = MessageSender(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=clock,
        ids=Uuid7Generator(),
        messaging=provider,
        templates=YamlTemplateCatalog.from_package(),
        phones=FernetPhoneCipher([Fernet.generate_key()]),
    )
    return SendReminder(sender=sender, ids=Uuid7Generator()), provider


def _consent(world: World, patient_id: str, *, whatsapp: bool = True) -> None:
    resp = _send(
        world.client_for(world.a.desk),
        "PUT",
        f"/api/v1/patients/{patient_id}/consent",
        {"whatsapp": whatsapp, "sms": False},
    )
    assert resp.status_code == 200, resp.get_json()


def _issued(
    world: World, follow_up: date | None
) -> tuple[FlaskClient, dict[str, Any], dict[str, Any]]:
    doctor, visit, rx = _draft(world)
    _consent(world, visit["patient_id"])
    filled = _fill(doctor, rx, follow_up_date=follow_up.isoformat() if follow_up else None)
    assert filled.status_code == 200, filled.get_json()
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert issued.status_code == 200, issued.get_json()
    return doctor, visit, issued.get_json()


def _reminders(db: Engine, **where: Any) -> list[Any]:
    clause = " AND ".join(f"{k} = :{k}" for k in where) or "true"
    with db.connect() as conn:
        return list(
            conn.execute(text(f"SELECT * FROM reminders WHERE {clause} ORDER BY created_at"), where)
        )


def _scalar(db: Engine, sql: str, **params: Any) -> Any:
    with db.connect() as conn:
        return conn.execute(text(sql), params).scalar()


# --- Automatic follow-ups (R1, R2, AC1) ---------------------------------------------------------


def test_r1_issuing_with_a_follow_up_schedules_it_for_0900_the_day_before(
    world: World, db: Engine
) -> None:
    follow_up = _today() + timedelta(days=5)
    _, _, rx = _issued(world, follow_up)
    [reminder] = _reminders(db, source_id=UUID(rx["id"]))
    assert (reminder.status, reminder.source, reminder.revision) == ("SCHEDULED", "PRESCRIPTION", 1)
    assert reminder.follow_up_date == follow_up
    assert reminder.due_at == _at_ist(follow_up - timedelta(days=1), 9)
    job = _job(db, f"reminder:{reminder.id}:1")
    assert job.kind == "send_reminder" and job.payload["revision"] == 1
    assert _scalar(db, "SELECT run_at FROM jobs WHERE id = :i", i=job.id) == reminder.due_at
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM audit_events WHERE action = 'reminder.scheduled'"
            " AND entity_id = :i",
            i=reminder.id,
        )
        == 1
    )


def test_r2_a_revision_moves_then_cancels_the_chains_one_reminder(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    doctor, _, v1 = _issued(world, _today() + timedelta(days=5))
    [reminder] = _reminders(db, source_id=UUID(v1["id"]))

    latest = v1

    def revise(follow_up: date | None) -> dict[str, Any]:
        nonlocal latest
        draft = _send(doctor, "POST", f"/api/v1/prescriptions/{latest['id']}/revise").get_json()
        assert (
            _fill(
                doctor, draft, follow_up_date=follow_up.isoformat() if follow_up else None
            ).status_code
            == 200
        )
        issued = _send(
            doctor, "POST", f"/api/v1/prescriptions/{draft['id']}/issue", {"revision": 2}
        )
        assert issued.status_code == 200, issued.get_json()
        latest = issued.get_json()
        return latest

    revise(_today() + timedelta(days=9))
    [moved] = _reminders(db, source_id=UUID(v1["id"]))
    assert (moved.id, moved.revision, moved.follow_up_date) == (
        reminder.id,
        2,
        _today() + timedelta(days=9),
    )
    # The job of revision 1 still runs at its time and does nothing (decision 1A).
    send, provider = _sender(session_factory, FakeClock(_at_ist(_today(), 10)))
    send(_job(db, f"reminder:{reminder.id}:1"))
    assert provider.calls == []

    v3 = revise(None)
    [cancelled] = _reminders(db, source_id=UUID(v1["id"]))
    assert (cancelled.status, cancelled.revision) == ("CANCELLED", 3)
    assert v3["version"] == 3


# --- Sending (R4, R5, AC2, decisions 2A, 3A, 6A) ------------------------------------------------


def test_fr_rem_01_a_due_reminder_sends_follow_up_due_and_shows_the_message_status(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    follow_up = _today() + timedelta(days=5)
    _, visit, rx = _issued(world, follow_up)
    [reminder] = _reminders(db, source_id=UUID(rx["id"]))
    send, provider = _sender(session_factory, FakeClock(reminder.due_at))
    send(_job(db, f"reminder:{reminder.id}:1"))
    [call] = provider.calls
    assert call.template.key == "follow_up_due"
    assert call.variables["doctor_name"] == world.a.doctor.display_name
    assert call.variables["clinic_phone"] == world.a.clinic.phone.e164  # type: ignore[union-attr]
    assert call.variables["follow_up_date"].endswith(str(follow_up.year))
    [after] = _reminders(db, id=reminder.id)
    assert after.status == "SENT"
    desk = world.client_for(world.a.desk)
    listed = desk.get(f"/api/v1/patients/{visit['patient_id']}/reminders").get_json()["items"]
    assert [(i["id"], i["status"], i["source"]) for i in listed] == [
        (str(reminder.id), "SENT", "PRESCRIPTION")
    ]
    assert (
        _scalar(db, "SELECT source_type FROM messages WHERE source_id = :i", i=reminder.id)
        == "REMINDER"
    )


def test_ac2_a_reminder_due_at_2215_is_deferred_to_0800(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, _, rx = _issued(world, _today() + timedelta(days=5))
    [reminder] = _reminders(db, source_id=UUID(rx["id"]))
    late = _at_ist(_today() + timedelta(days=4), 22, 15)
    send, provider = _sender(session_factory, FakeClock(late))
    send(_job(db, f"reminder:{reminder.id}:1"))
    assert provider.calls == []
    [deferred] = _reminders(db, id=reminder.id)
    morning = _at_ist(_today() + timedelta(days=5), 8)
    assert (deferred.status, deferred.revision, deferred.due_at) == ("SCHEDULED", 2, morning)
    next_job = _job(db, f"reminder:{reminder.id}:2")
    assert _scalar(db, "SELECT run_at FROM jobs WHERE id = :i", i=next_job.id) == morning
    send_later, provider_later = _sender(session_factory, FakeClock(morning))
    send_later(next_job)
    assert len(provider_later.calls) == 1


def test_r5_no_consent_at_send_time_skips_and_6a_no_clinic_phone_fails(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, visit, rx = _issued(world, _today() + timedelta(days=5))
    [reminder] = _reminders(db, source_id=UUID(rx["id"]))
    desk = world.client_for(world.a.desk)
    assert _send(desk, "POST", f"/api/v1/patients/{visit['patient_id']}/opt-out").status_code == 200
    send, provider = _sender(session_factory, FakeClock(reminder.due_at))
    send(_job(db, f"reminder:{reminder.id}:1"))
    assert provider.calls == []
    assert _reminders(db, id=reminder.id)[0].status == "SKIPPED_NO_CONSENT"
    assert _scalar(db, "SELECT count(*) FROM messages WHERE source_id = :i", i=reminder.id) == 0


def test_6a_a_clinic_without_a_phone_fails_the_reminder_with_a_reason(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, _, rx = _issued(world, _today() + timedelta(days=5))
    [reminder] = _reminders(db, source_id=UUID(rx["id"]))
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinics SET phone_e164 = NULL WHERE id = :c"), {"c": world.a.clinic.id}
        )
    send, provider = _sender(session_factory, FakeClock(reminder.due_at))
    send(_job(db, f"reminder:{reminder.id}:1"))
    assert provider.calls == []
    after = _reminders(db, id=reminder.id)[0]
    assert (after.status, after.error_code) == ("FAILED", "REM_CLINIC_PHONE_MISSING")


# --- Manual reminders (R3, FR-REM-02, decision 5A) ----------------------------------------------


def test_fr_rem_02_staff_schedule_move_and_cancel_a_reminder(world: World, db: Engine) -> None:
    from tests.integration.test_appointments_http import _patient

    desk = world.client_for(world.a.desk)
    patient = _patient(desk, "Asha Rao")
    url = f"/api/v1/patients/{patient}/reminders"
    body = {
        "doctor_id": str(world.a.doctor.id),
        "follow_up_date": (_today() + timedelta(days=3)).isoformat(),
    }
    refused = _send(desk, "POST", url, body)
    assert (refused.status_code, refused.get_json()["error"]["code"]) == (409, "REM_NO_CONSENT")
    _consent(world, patient)
    past = _send(desk, "POST", url, {**body, "follow_up_date": _today().isoformat()})
    assert (past.status_code, past.get_json()["error"]["code"]) == (422, "REM_IN_PAST")

    created = _send(desk, "POST", url, body)
    assert created.status_code == 201, created.get_json()
    reminder = created.get_json()
    assert (reminder["status"], reminder["source"], reminder["prescription_id"]) == (
        "SCHEDULED",
        "MANUAL",
        None,
    )
    one = f"/api/v1/reminders/{reminder['id']}"
    both = _send(desk, "PATCH", one, {"follow_up_date": body["follow_up_date"], "cancel": True})
    assert both.status_code == 422
    moved = _send(
        desk, "PATCH", one, {"follow_up_date": (_today() + timedelta(days=6)).isoformat()}
    ).get_json()
    assert (moved["revision"], moved["follow_up_date"]) == (
        2,
        (_today() + timedelta(days=6)).isoformat(),
    )
    assert (
        _scalar(
            db, "SELECT count(*) FROM jobs WHERE dedupe_key = :k", k=f"reminder:{reminder['id']}:2"
        )
        == 1
    )
    cancelled = _send(desk, "PATCH", one, {"cancel": True}).get_json()
    assert cancelled["status"] == "CANCELLED"
    again = _send(desk, "PATCH", one, {"cancel": True})
    assert (again.status_code, again.get_json()["error"]["code"]) == (409, "REM_NOT_SCHEDULED")
    actions = [r[0] for r in _audit_actions(db, reminder["id"])]
    assert actions == ["reminder.scheduled", "reminder.rescheduled", "reminder.cancelled"]

    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinics SET phone_e164 = NULL WHERE id = :c"), {"c": world.a.clinic.id}
        )
    no_phone = _send(desk, "POST", url, body)
    assert (no_phone.status_code, no_phone.get_json()["error"]["code"]) == (
        409,
        "REM_CLINIC_PHONE_MISSING",
    )


def test_nfr_08_another_clinics_patient_and_reminder_are_404(world: World) -> None:
    from tests.integration.test_appointments_http import _patient

    desk_a = world.client_for(world.a.desk)
    patient = _patient(desk_a, "Asha Rao")
    _consent(world, patient)
    created = _send(
        desk_a,
        "POST",
        f"/api/v1/patients/{patient}/reminders",
        {
            "doctor_id": str(world.a.doctor.id),
            "follow_up_date": (_today() + timedelta(days=3)).isoformat(),
        },
    ).get_json()
    desk_b = world.client_for(world.b.desk)
    assert desk_b.get(f"/api/v1/patients/{patient}/reminders").status_code == 404
    assert (
        _send(desk_b, "PATCH", f"/api/v1/reminders/{created['id']}", {"cancel": True}).status_code
        == 404
    )


def _audit_actions(db: Engine, entity_id: str) -> list[Any]:
    with db.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT action FROM audit_events WHERE entity_id = :i ORDER BY occurred_at, id"
                ),
                {"i": entity_id},
            )
        )


# --- Pending follow-ups (R17, FR-REM-07) --------------------------------------------------------


def _past_prescription(
    uow_factory: UowFactory, world: World, patient_id: str, *, days_ago: int, follow_up_after: int
) -> UUID:
    """An issued prescription on a completed visit ``days_ago``, follow-up some days later."""
    visit_id = _past_visit(uow_factory, world, patient_id, days_ago)
    with uow_factory() as uow:
        clinic = uow.clinics.get(world.a.clinic.id)
        staff = uow.tenant(world.a.clinic.id)
        visit = staff.visits.get(visit_id)
        assert clinic is not None and visit is not None
        then = visit.started_at
        rx = Prescription.first_draft(
            visit, id=new_id(), created_by=world.a.doctor_user.id, now=then
        )
        rx.replace_body(
            items=[PrescriptionItem.create(id=new_id(), position=1, medicine_name="Tab Z")],
            advice=Advice(),
            follow_up_date=then.date() + timedelta(days=follow_up_after),
            seen_revision=1,
            today=then.date(),
            now=then,
        )
        staff.prescriptions.add(rx)
        doctor = staff.doctors.get(world.a.doctor.id)
        patient = staff.patients.get(UUID(patient_id))
        assert doctor is not None and patient is not None
        rx.issue(
            doctor=doctor,
            clinic=clinic,
            language=patient.language,
            may_message=False,
            seen_revision=2,
            today=then.date(),
            now=then,
        )
        staff.prescriptions.update(rx)
        uow.commit()
    return rx.id


def test_r17_pending_follow_ups_lists_overdue_patients_oldest_first(
    world: World, uow_factory: UowFactory
) -> None:
    from tests.integration.test_appointments_http import _patient

    desk = world.client_for(world.a.desk)
    late, later, returned = (_patient(desk, n) for n in ("Asha Rao", "Bina Shah", "Chitra Das"))
    # _past_visit makes a session per day for the clinic's doctor: one day each.
    late_rx = _past_prescription(uow_factory, world, late, days_ago=40, follow_up_after=5)
    later_rx = _past_prescription(uow_factory, world, later, days_ago=20, follow_up_after=5)
    _past_prescription(uow_factory, world, returned, days_ago=41, follow_up_after=5)
    _past_visit(uow_factory, world, returned, 10)  # came back after the follow-up date

    items = desk.get("/api/v1/follow-ups/pending").get_json()["items"]
    ours = [i for i in items if i["patient_id"] in {late, later, returned}]
    assert [(i["patient_id"], i["prescription_id"]) for i in ours] == [
        (late, str(late_rx)),
        (later, str(later_rx)),
    ]
    assert ours[0]["patient_code"] and ours[0]["reminder_status"] is None
    page = desk.get("/api/v1/follow-ups/pending?limit=1&offset=1").get_json()
    assert (page["limit"], page["offset"], len(page["items"])) == (1, 1, 1)
    assert desk.get("/api/v1/follow-ups/pending?limit=0").status_code == 422
    assert (
        world.client_for(world.b.desk).get("/api/v1/follow-ups/pending").get_json()["items"] == []
    )


# --- Automatic no-show (appointments R10, decision 4A) ------------------------------------------


def _session_with_booking(
    uow_factory: UowFactory, world: World, patient_id: str, ends: datetime
) -> UUID:
    starts = ends - timedelta(hours=2)
    plan = PlannedSession(
        world.a.doctor.id,
        starts.astimezone(KOLKATA).date(),
        starts,
        ends,
        BookingMode.TOKENS,
        None,
        5,
    )
    with uow_factory() as uow:
        staff = uow.tenant(world.a.clinic.id)
        session = ClinicSession.from_plan(
            plan, id=new_id(), clinic_id=world.a.clinic.id, now=starts
        )
        staff.sessions.add_missing([session])
        appointment = Appointment.book(
            session, id=new_id(), patient_id=UUID(patient_id), active=[], now=starts
        )
        staff.sessions.update(session)
        staff.appointments.add(appointment)
        uow.commit()
    return appointment.id


def _system_job(kind: str, clinic_id: UUID | None = None) -> ClaimedJob:
    return ClaimedJob(
        id=new_id(),
        kind=kind,
        clinic_id=clinic_id,
        payload={},
        attempts=1,
        max_attempts=5,
        request_id="req-no-show",
        locked_by="test",
    )


def test_r10_bookings_an_hour_past_their_session_become_no_show(
    world: World, db: Engine, uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    from tests.integration.test_appointments_http import _patient

    desk = world.client_for(world.a.desk)
    now = datetime(2030, 1, 7, 9, 0, tzinfo=UTC)
    overdue = _session_with_booking(
        uow_factory, world, _patient(desk, "Asha Rao"), now - timedelta(minutes=61)
    )
    recent = _session_with_booking(
        uow_factory, world, _patient(desk, "Bina Shah"), now - timedelta(minutes=30)
    )
    clock = FakeClock(now)
    ids = Uuid7Generator()
    SweepNoShows(uow=SqlAlchemyUnitOfWork(session_factory), clock=clock, ids=ids)(
        _system_job("schedule_no_shows")
    )
    key = _scalar(
        db,
        "SELECT dedupe_key FROM jobs WHERE kind = 'mark_no_shows' AND clinic_id = :c",
        c=world.a.clinic.id,
    )
    assert key and key.startswith(f"mark_no_shows:{world.a.clinic.id}:")
    MarkNoShows(uow=SqlAlchemyUnitOfWork(session_factory), clock=clock, ids=ids)(
        _system_job("mark_no_shows", world.a.clinic.id)
    )
    status = "SELECT status FROM appointments WHERE id = :i"
    assert (_scalar(db, status, i=overdue), _scalar(db, status, i=recent)) == ("NO_SHOW", "BOOKED")
    assert (
        _scalar(
            db,
            "SELECT changed_by IS NULL FROM appointment_status_history"
            " WHERE appointment_id = :i AND to_status = 'NO_SHOW'",
            i=overdue,
        )
        is True
    )
    with db.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT actor_type, metadata FROM audit_events WHERE entity_id = :i"
                " AND action = 'appointment.status_changed'"
            ),
            {"i": overdue},
        ).one()
    assert audit.actor_type == "SYSTEM" and audit.metadata["automatic"] == "true"
    assert (
        _scalar(
            db,
            "SELECT count(*) FROM jobs WHERE kind = 'mark_no_shows' AND clinic_id = :c",
            c=world.b.clinic.id,
        )
        == 0
    )
