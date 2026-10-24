"""The patient's own medicine-plan settings (M6b-P3; patient portal R31, R37-R40; D6).

- ``SlotTimes``: when *this person's* morning, afternoon, evening and night are, on the account
  (defaults 08:00, 14:00, 18:00, 21:00). They place the plan's slots on a clock; they never change
  which slots the doctor marked.
- ``MedicineReminderPref``: whether this person wants a reminder for one line of one version in
  one of the slots the doctor marked, and at what time (``remind_at``; ``None`` = the slot's own
  time). Stored only; P6 delivers them. A preference never changes a prescription, a revision
  never inherits one, and SOS, ONCE and CUSTOM lines have none (``plan.is_remindable``).

Tenant data: a preference names one clinic's prescription and lives in that clinic's rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from itertools import pairwise
from uuid import UUID

from mediease_api.domain.prescriptions.schedule import DAY_ORDER, Slot
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

EARLIEST = time(5, 0)
LATEST = time(23, 30)


def check_clock_time(value: time, field: str) -> time:
    """R31: 05:00-23:30, to the minute (no seconds, no time zone)."""
    if value.tzinfo is not None or value.second or value.microsecond:
        raise InvalidValue(field, "must be a time of day as HH:MM")
    if not EARLIEST <= value <= LATEST:
        raise InvalidValue(field, "must be between 05:00 and 23:30")
    return value


@dataclass(frozen=True, slots=True)
class SlotTimes:
    """One person's times of day, each 05:00-23:30 and later than the one before."""

    morning: time = time(8, 0)
    afternoon: time = time(14, 0)
    evening: time = time(18, 0)
    night: time = time(21, 0)

    def __post_init__(self) -> None:
        values = [self.at(slot) for slot in DAY_ORDER]
        for slot, value in zip(DAY_ORDER, values, strict=True):
            check_clock_time(value, f"slot_times.{slot.value.lower()}")
        if any(a >= b for a, b in pairwise(values)):
            raise InvalidValue("slot_times", "must run morning, afternoon, evening, night")

    def at(self, slot: Slot) -> time:
        return {
            Slot.MORNING: self.morning,
            Slot.AFTERNOON: self.afternoon,
            Slot.EVENING: self.evening,
            Slot.NIGHT: self.night,
        }[slot]


@dataclass(slots=True)
class MedicineReminderPref:
    """Build with ``create``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    account_id: UUID
    prescription_id: UUID
    item_id: UUID
    slot: Slot
    enabled: bool
    remind_at: time | None
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
        slot: Slot,
        enabled: bool,
        remind_at: time | None,
        now: datetime,
    ) -> MedicineReminderPref:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            account_id=account_id,
            prescription_id=prescription_id,
            item_id=item_id,
            slot=slot,
            enabled=enabled,
            remind_at=check_clock_time(remind_at, "remind_at") if remind_at is not None else None,
            created_at=now,
            updated_at=now,
        )

    def change(self, *, enabled: bool, remind_at: time | None, now: datetime) -> bool:
        """Returns False when nothing changed."""
        remind_at = check_clock_time(remind_at, "remind_at") if remind_at is not None else None
        if (enabled, remind_at) == (self.enabled, self.remind_at):
            return False
        self.enabled, self.remind_at = enabled, remind_at
        self.updated_at = require_utc(now, "now")
        return True
