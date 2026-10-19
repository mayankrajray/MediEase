"""Reminder rules and states, and the automatic no-show (M5-P4; spec R1, R2, R4; AC1, AC2; R10)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.queue import (
    NO_SHOW_AFTER,
    mark_no_show_automatically,
    no_show_cutoff,
)
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.messaging.formatting import follow_up_date_text
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.reminders.errors import NotScheduled
from mediease_api.domain.reminders.reminder import Reminder, ReminderSource, ReminderStatus
from mediease_api.domain.reminders.rules import (
    follow_up_due_at,
    in_quiet_hours,
    outside_quiet_hours,
)
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession, Session
from tests.builders import new_id

IST = "Asia/Kolkata"


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# --- When (R1, R4) ------------------------------------------------------------------------------


def test_ac1_a_follow_up_on_20_sep_is_due_19_sep_0900_ist() -> None:
    assert follow_up_due_at(date(2026, 9, 20), IST, _utc(2026, 9, 1)) == _utc(2026, 9, 19, 3, 30)


def test_r1_a_due_time_already_past_is_now_and_never_in_quiet_hours() -> None:
    noon_ist = _utc(2026, 9, 19, 6, 30)
    assert follow_up_due_at(date(2026, 9, 20), IST, noon_ist) == noon_ist
    late = _utc(2026, 9, 19, 16, 45)  # 22:15 IST
    assert follow_up_due_at(date(2026, 9, 20), IST, late) == _utc(2026, 9, 20, 2, 30)


def test_ac2_a_job_due_at_2215_ist_runs_at_0800_the_next_day() -> None:
    assert in_quiet_hours(_utc(2026, 9, 19, 16, 45), IST)
    assert outside_quiet_hours(_utc(2026, 9, 19, 16, 45), IST) == _utc(2026, 9, 20, 2, 30)
    early = _utc(2026, 9, 19, 1, 0)  # 06:30 IST: the same day's 08:00
    assert outside_quiet_hours(early, IST) == _utc(2026, 9, 19, 2, 30)
    edge = _utc(2026, 9, 19, 2, 30)  # 08:00 sharp is allowed; 21:00 sharp is not
    assert not in_quiet_hours(edge, IST) and outside_quiet_hours(edge, IST) == edge
    assert in_quiet_hours(_utc(2026, 9, 19, 15, 30), IST)
    assert not in_quiet_hours(_utc(2026, 9, 19, 15, 29), IST)


def test_follow_up_dates_read_in_both_languages() -> None:
    assert follow_up_date_text(date(2026, 9, 20), Language.EN) == "Sun 20 Sep 2026"
    assert follow_up_date_text(date(2026, 9, 20), Language.HI) == "20/09/2026"


# --- States (decisions 1A, 3A) ------------------------------------------------------------------

NOW = _utc(2026, 9, 1, 6)


def _reminder() -> Reminder:
    return Reminder.schedule(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        doctor_id=new_id(),
        source=ReminderSource.MANUAL,
        source_id=None,
        follow_up_date=date(2026, 9, 20),
        due_at=_utc(2026, 9, 19, 3, 30),
        created_by=new_id(),
        now=NOW,
    )


def test_1a_every_move_bumps_the_revision() -> None:
    reminder = _reminder()
    assert (reminder.status, reminder.revision) == (ReminderStatus.SCHEDULED, 1)
    reminder.move(follow_up_date=date(2026, 9, 22), due_at=_utc(2026, 9, 21, 3, 30), now=NOW)
    reminder.defer(_utc(2026, 9, 21, 4), NOW)
    assert (reminder.revision, reminder.follow_up_date) == (3, date(2026, 9, 22))
    reminder.cancel(by=None, now=NOW)
    assert (reminder.status, reminder.revision, reminder.cancelled_at) == (
        ReminderStatus.CANCELLED,
        4,
        NOW,
    )
    with pytest.raises(NotScheduled):
        reminder.move(follow_up_date=date(2026, 9, 23), due_at=NOW, now=NOW)


def test_3a_a_sent_reminder_is_handed_to_its_message_and_is_final() -> None:
    reminder = _reminder()
    reminder.handed_off(NOW)
    reminder.handed_off(NOW)  # a retry of the same message
    assert reminder.status is ReminderStatus.SENT
    for change in (
        lambda: reminder.cancel(by=None, now=NOW),
        lambda: reminder.skipped_no_consent(NOW),
        lambda: reminder.defer(NOW, NOW),
    ):
        with pytest.raises(NotScheduled):
            change()
    skipped, failed = _reminder(), _reminder()
    skipped.skipped_no_consent(NOW)
    failed.failed("REM_CLINIC_PHONE_MISSING", NOW)
    assert (skipped.status, failed.status, failed.error_code) == (
        ReminderStatus.SKIPPED_NO_CONSENT,
        ReminderStatus.FAILED,
        "REM_CLINIC_PHONE_MISSING",
    )


# --- Automatic no-show (appointments R10) -------------------------------------------------------


def _booked(ends: datetime) -> tuple[Appointment, Session]:
    starts = ends - timedelta(hours=2)
    plan = PlannedSession(new_id(), starts.date(), starts, ends, BookingMode.TOKENS, None, 5)
    session = Session.from_plan(plan, id=new_id(), clinic_id=new_id(), now=starts)
    appointment = Appointment.book(session, id=new_id(), patient_id=new_id(), active=[], now=starts)
    return appointment, session


def test_r10_a_booking_becomes_no_show_an_hour_after_its_session() -> None:
    ends = _utc(2026, 9, 1, 18, 0)  # 23:30 IST: the hour ends after midnight, still applies
    appointment, session = _booked(ends)
    early = ends + NO_SHOW_AFTER - timedelta(seconds=1)
    assert not mark_no_show_automatically(appointment, session, now=early)
    later = ends + NO_SHOW_AFTER  # at end + 60 minutes exactly
    assert no_show_cutoff(later) == ends
    assert mark_no_show_automatically(appointment, session, now=later)
    assert (appointment.status, appointment.updated_at) == (AppointmentStatus.NO_SHOW, later)
    assert not mark_no_show_automatically(appointment, session, now=later)  # once only
