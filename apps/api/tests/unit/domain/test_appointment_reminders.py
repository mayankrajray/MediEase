"""Appointment reminder times, the audit catalogue and related domain rules (M6a-P8)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.catalogue import ACTIONS, AuditCategory, actions_in, describe
from mediease_api.domain.notifications.notification import PersonName, bookings_to_move_title
from mediease_api.domain.reminders.reminder import Reminder, ReminderKind, ReminderStatus
from mediease_api.domain.reminders.rules import appointment_reminder_times
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, a_clinic, new_id

TZ = "Asia/Kolkata"
IST = ZoneInfo(TZ)


def _ist(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=IST).astimezone(UTC)


def _times(
    starts: datetime, now: datetime, *, evening: bool = True, hours: int = 2
) -> list[datetime]:
    return appointment_reminder_times(
        starts_at=starts, timezone=TZ, now=now, evening_before=evening, hours_before=hours
    )


def test_fr_apt_08_the_evening_before_and_hours_before_by_default() -> None:
    assert _times(_ist(10, 11), _ist(1, 12)) == [_ist(9, 19), _ist(10, 9)]


def test_fr_apt_08_quiet_hours_move_a_reminder_to_eight_but_never_past_the_visit() -> None:
    assert _times(_ist(10, 9), _ist(1, 12)) == [_ist(9, 19), _ist(10, 8)]  # 07:00 -> 08:00
    assert _times(_ist(10, 8), _ist(1, 12)) == [_ist(9, 19)]  # 06:00 -> 08:00 is the start
    # 21:00 for a 22:00 visit is quiet; the next 08:00 is after the visit, so it is not sent.
    assert _times(_ist(10, 22), _ist(1, 12), hours=1) == [_ist(9, 19)]


def test_fr_apt_08_nothing_due_within_an_hour_of_booking_or_already_past() -> None:
    booked = _ist(10, 18, 30)
    assert _times(_ist(11, 10), booked) == [_ist(11, 8)]  # 19:00 is 30 min away
    assert (
        _times(_ist(10, 20), _ist(10, 17, 30)) == []
    )  # 18:00 is 30 min away; the day before passed
    assert _times(_ist(10, 11), _ist(10, 10)) == []


def test_fr_apt_08_each_reminder_can_be_turned_off() -> None:
    assert _times(_ist(10, 11), _ist(1, 12), evening=False) == [_ist(10, 9)]
    assert _times(_ist(10, 11), _ist(1, 12), hours=0) == [_ist(9, 19)]
    assert _times(_ist(10, 11), _ist(1, 12), evening=False, hours=0) == []


def test_an_appointment_reminder_is_cancelled_with_a_reason() -> None:
    reminder = Reminder.for_appointment(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        doctor_id=new_id(),
        appointment_id=new_id(),
        visit_date=date(2026, 11, 10),
        due_at=_ist(9, 19),
        created_by=None,
        now=NOW,
    )
    assert reminder.kind is ReminderKind.APPOINTMENT and reminder.follows_appointment
    reminder.cancel(by=None, now=NOW, code="REM_APPOINTMENT_CHANGED")
    assert (reminder.status, reminder.error_code, reminder.revision) == (
        ReminderStatus.CANCELLED,
        "REM_APPOINTMENT_CHANGED",
        2,
    )


def test_a_clinic_chooses_its_reminders_within_bounds() -> None:
    clinic = a_clinic()
    assert (clinic.reminder_evening_before, clinic.reminder_hours_before) == (True, 2)
    clinic.change_reminders(now=NOW, evening_before=False, hours_before=6)
    assert (clinic.reminder_evening_before, clinic.reminder_hours_before) == (False, 6)
    clinic.change_reminders(now=NOW)  # nothing given, nothing changes
    assert clinic.reminder_hours_before == 6
    for wrong in (-1, 7):
        with pytest.raises(InvalidValue):
            clinic.change_reminders(now=NOW, hours_before=wrong)


def test_fr_aud_03_every_action_has_words_and_a_category() -> None:
    assert set(ACTIONS) == set(AuditAction)
    assert all(info.label and info.label[0].isupper() for info in ACTIONS.values())
    assert "appointment.cancelled" in actions_in(frozenset({AuditCategory.APPOINTMENTS}))
    assert describe("retired.action").label == "retired.action"


def test_fr_apt_09_the_bookings_to_move_title_names_the_doctor_day_and_count() -> None:
    doctor = PersonName("Dr. Sample")
    assert bookings_to_move_title(doctor, 3, date(2026, 10, 24)) == (
        "Dr. Sample on leave 24 Oct: 3 bookings to move"
    )
    assert (
        bookings_to_move_title(doctor, 1, None)
        == "Dr. Sample's schedule changed: 1 booking to move"
    )
