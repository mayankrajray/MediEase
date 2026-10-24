"""Dose records (M6b-P3b; D4, D5; patient portal R45-R53). Pure."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from mediease_api.domain.portal.doses import (
    MARK_WINDOW,
    RETENTION,
    DoseRecord,
    DoseState,
    DoseStatus,
    scheduled_at,
    status_of,
    window_open,
)
from mediease_api.domain.prescriptions.schedule import Slot
from tests.builders import new_id

TZ = "Asia/Kolkata"
DAY = date(2026, 10, 25)
# 08:00 in Kolkata on DAY is 02:30 UTC.
DUE = datetime(2026, 10, 25, 2, 30, tzinfo=UTC)


def record(state: DoseState = DoseState.TAKEN, *, course_end: date | None = None) -> DoseRecord:
    return DoseRecord.create(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        account_id=new_id(),
        prescription_id=new_id(),
        item_id=new_id(),
        on_date=DAY,
        slot=Slot.MORNING,
        state=state,
        course_end=course_end,
        now=DUE + timedelta(minutes=12),
    )


def test_a_dose_is_due_at_the_persons_slot_time_on_the_clinics_clock() -> None:
    assert scheduled_at(DAY, time(8, 0), TZ) == DUE


@pytest.mark.parametrize(
    ("on_date", "today", "now", "open_"),
    [
        (DAY, DAY, DUE - timedelta(hours=7), True),  # 00:30 on the dose's day, before its time
        (DAY, DAY, DUE + timedelta(minutes=12), True),
        (DAY, DAY + timedelta(days=2), DUE + MARK_WINDOW, True),  # exactly 48 hours after
        (DAY, DAY + timedelta(days=2), DUE + MARK_WINDOW + timedelta(seconds=1), False),
        (DAY, DAY - timedelta(days=1), DUE - timedelta(days=1), False),  # a future day
    ],
)
def test_r46_the_window_runs_from_the_days_start_to_48_hours_after_the_dose(
    on_date: date, today: date, now: datetime, open_: bool
) -> None:
    assert window_open(on_date=on_date, due=DUE, today=today, now=now) is open_


def test_r47_not_recorded_is_derived_once_the_time_has_passed_and_never_stored() -> None:
    assert status_of(None, due=DUE, now=DUE - timedelta(minutes=1)) is DoseStatus.UPCOMING
    assert status_of(None, due=DUE, now=DUE + timedelta(minutes=1)) is DoseStatus.NOT_RECORDED
    assert status_of(record(), due=DUE, now=DUE) is DoseStatus.TAKEN
    # There is no stored state for it: only what the patient marked.
    assert {s.value for s in DoseState} == {"TAKEN", "SKIPPED"}


def test_r45_a_change_moves_the_time_marked_and_the_same_mark_changes_nothing() -> None:
    dose = record()
    assert dose.marked_at == DUE + timedelta(minutes=12)
    later = DUE + timedelta(hours=1)
    assert not dose.change(DoseState.TAKEN, now=later)
    assert dose.change(DoseState.SKIPPED, now=later)
    assert (dose.state, dose.marked_at, dose.updated_at) == (DoseState.SKIPPED, later, later)


def test_r53_kept_a_year_after_the_course_end_or_the_dose_date_when_open_ended() -> None:
    assert (
        record(course_end=DAY + timedelta(days=4)).keep_until == DAY + timedelta(days=4) + RETENTION
    )
    assert record(course_end=None).keep_until == DAY + RETENTION
