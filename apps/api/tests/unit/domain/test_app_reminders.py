"""M7e-E4 (spec web-push R41, R43): the reminder notices' titles and the SENT_IN_APP status."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.notifications import (
    Names,
    PatientNotification,
    PatientNotificationKind,
    render_title,
)
from mediease_api.domain.reminders.errors import NotScheduled
from mediease_api.domain.reminders.reminder import Reminder, ReminderStatus
from tests.builders import new_id

NOW = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)
NAMES = Names("Sample Clinic", "Dr Sample", "Asia/Kolkata")


def _notice(kind: PatientNotificationKind, params: dict[str, str]) -> PatientNotification:
    return PatientNotification.create(
        id=new_id(),
        clinic_id=new_id(),
        account_id=new_id(),
        kind=kind,
        event_key=f"{kind.value}:{new_id()}",
        entity=("reminder", new_id()),
        link="/portal/appointments",
        params=params,
        now=NOW,
    )


def test_r41_an_appointment_reminder_names_the_time_doctor_and_clinic() -> None:
    notice = _notice(
        PatientNotificationKind.APPOINTMENT_REMINDER,
        {"at": "2026-11-17T04:30:00+00:00", "doctor_id": str(new_id()), "token": "4"},
    )
    assert render_title(notice, NAMES, Language.EN) == (
        "Reminder: 17 Nov, token 4 with Dr Sample at Sample Clinic"
    )
    assert render_title(notice, NAMES, Language.HI) == (
        "रिमाइंडर: 17 नव॰, टोकन 4, Dr Sample (Sample Clinic)"
    )


def test_r45_a_follow_up_names_the_day_and_a_bad_date_says_nothing() -> None:
    good = _notice(PatientNotificationKind.FOLLOW_UP_DUE, {"date": "2026-11-24"})
    assert render_title(good, NAMES, Language.EN) == (
        "Follow-up due 24 Nov with Dr Sample at Sample Clinic"
    )
    bad = _notice(PatientNotificationKind.FOLLOW_UP_DUE, {"date": "soon"})
    assert render_title(bad, NAMES, Language.EN) == "Follow-up due with Dr Sample at Sample Clinic"
    assert render_title(bad, NAMES, Language.HI) == "Dr Sample (Sample Clinic) के साथ फ़ॉलो-अप"


def _reminder() -> Reminder:
    return Reminder.for_appointment(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        doctor_id=new_id(),
        appointment_id=new_id(),
        visit_date=date(2026, 11, 17),
        due_at=NOW,
        created_by=None,
        now=NOW,
    )


def test_r43_sent_in_app_is_final() -> None:
    reminder = _reminder()
    reminder.sent_in_app(NOW)
    assert (reminder.status, reminder.error_code) == (ReminderStatus.SENT_IN_APP, None)
    with pytest.raises(NotScheduled):
        reminder.cancel(by=None, now=NOW)
