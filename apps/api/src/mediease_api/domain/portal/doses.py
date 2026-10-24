"""Dose records: the patient's own Taken / Skipped marks (M6b-P3b; D4, D5; portal R45-R54).

A record says one thing: the person marked one scheduled dose of one line of one prescription
**version** Taken or Skipped, at ``marked_at``. Nothing else is stored:

- a past dose with no record is **Not recorded**, derived when it is read (R47), never stored,
  never called missed and never given a reason;
- only timed entries of the plan can be marked (the engine decides which those are), from 00:00
  of the dose's day on the clinic's calendar until 48 hours after its scheduled time; never a
  future day (R46);
- records stay with the version and line they were made for (R49).

Health data (C3, R51): private to the patient account, no audit row per change, no state, medicine
or time in any log. Kept one year after the course ends, or after the dose date for open-ended
courses: a product period **subject to privacy and legal review** (R53).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from mediease_api.domain.prescriptions.schedule import Slot
from mediease_api.domain.shared.errors import DomainError
from mediease_api.domain.shared.time import require_utc

# R46: a dose can be marked, changed or cleared until this long after its scheduled time.
MARK_WINDOW = timedelta(hours=48)
# R53: records are deleted this long after the course end (or the dose date, open-ended).
RETENTION = timedelta(days=365)


class DoseState(StrEnum):
    """What the patient marked. Not recorded and Upcoming are read, never stored."""

    TAKEN = "TAKEN"
    SKIPPED = "SKIPPED"


class DoseStatus(StrEnum):
    """What a scheduled dose shows (R45-R47)."""

    TAKEN = "TAKEN"
    SKIPPED = "SKIPPED"
    NOT_RECORDED = "NOT_RECORDED"
    UPCOMING = "UPCOMING"


class DoseNotMarkable(DomainError):
    """R46: outside the dose's window (a future day, or more than 48 hours after its time)."""

    code = "PRT_DOSE_NOT_MARKABLE"

    def __init__(self) -> None:
        super().__init__(
            "This dose can only be marked from the start of its day until 48 hours after its time."
        )


def scheduled_at(on_date: date, slot_time: time, timezone: str) -> datetime:
    """The dose's time as an instant: its day and the person's slot time, on the clinic's clock."""
    return datetime.combine(on_date, slot_time, tzinfo=ZoneInfo(timezone)).astimezone(UTC)


def window_open(*, on_date: date, due: datetime, today: date, now: datetime) -> bool:
    """R46: from 00:00 of the dose's day (so never a future day) to 48 hours after ``due``."""
    now = require_utc(now, "now")
    return on_date <= today and now <= require_utc(due, "due") + MARK_WINDOW


def status_of(record: DoseRecord | None, *, due: datetime, now: datetime) -> DoseStatus:
    """R47: a record's state; else Not recorded once its time has passed, Upcoming before."""
    if record is not None:
        return DoseStatus(record.state.value)
    return DoseStatus.NOT_RECORDED if require_utc(now, "now") > due else DoseStatus.UPCOMING


@dataclass(slots=True)
class DoseRecord:
    """Build with ``create``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    account_id: UUID
    prescription_id: UUID
    item_id: UUID
    on_date: date
    slot: Slot
    state: DoseState
    marked_at: datetime
    # R53: when the purge may delete it (course end, or the dose date if open-ended, + 1 year).
    keep_until: date
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        account_id: UUID,
        prescription_id: UUID,
        item_id: UUID,
        on_date: date,
        slot: Slot,
        state: DoseState,
        course_end: date | None,
        now: datetime,
    ) -> DoseRecord:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            account_id=account_id,
            prescription_id=prescription_id,
            item_id=item_id,
            on_date=on_date,
            slot=slot,
            state=state,
            marked_at=now,
            keep_until=(course_end or on_date) + RETENTION,
            created_at=now,
            updated_at=now,
        )

    def change(self, state: DoseState, *, now: datetime) -> bool:
        """A new mark; the time marked moves with it. Returns False when it already was this."""
        if state is self.state:
            return False
        self.state = state
        self.marked_at = self.updated_at = require_utc(now, "now")
        return True
