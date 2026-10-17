"""Weekly blocks: the rules sessions are generated from (spec R3, R14, R15).

A block is wall-clock time in the clinic's zone: a weekday (0 = Monday … 6 = Sunday, as
``date.weekday()``), a start and an end time. An end at or before the start means the block ends
the next day (decision D2), so 23:00-01:00 is two hours. Every block lasts 15 minutes to 12 hours,
which keeps a daytime typo such as 13:00-10:00 (21 hours) from passing as an overnight shift.

Overlap is checked on the circle of the week: each block is an interval of minutes since Monday
00:00, wrapping at 7 x 24 h, so an overnight block on day N collides with an early block on day N+1
and Sunday night with Monday morning.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from uuid import UUID

from mediease_api.domain.scheduling.errors import InvalidBlock, ModeIncompatible, ScheduleOverlap
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

MINUTES_PER_DAY = 24 * 60
MINUTES_PER_WEEK = 7 * MINUTES_PER_DAY
MIN_BLOCK_MINUTES = 15
MAX_BLOCK_MINUTES = 12 * 60
SLOT_MINUTES = range(5, 121)
CAPACITY = range(1, 501)


def _minute_of_day(value: time, field: str) -> int:
    if value.second or value.microsecond or value.tzinfo is not None:
        raise InvalidValue(field, "must be a whole minute in the clinic's local time")
    return value.hour * 60 + value.minute


def block_minutes(start: time, end: time) -> int:
    """Length in minutes; an end at or before the start is on the next day (D2)."""
    s = _minute_of_day(start, "start_time")
    e = _minute_of_day(end, "end_time")
    return e - s if e > s else e + MINUTES_PER_DAY - s


@dataclass(frozen=True, slots=True)
class BlockShape:
    """The bookable part of a block: times plus what the booking modes need."""

    start_time: time
    end_time: time
    slot_minutes: int | None
    capacity: int | None

    @property
    def minutes(self) -> int:
        return block_minutes(self.start_time, self.end_time)

    @property
    def overnight(self) -> bool:
        return self.end_time <= self.start_time

    def capacity_for(self, mode: BookingMode) -> int:
        """Places in a session: length / slot length in slot mode (D3), stated in token mode."""
        if mode is BookingMode.SLOTS:
            if self.slot_minutes is None:
                raise ModeIncompatible(mode.value, "slot length")
            return self.minutes // self.slot_minutes
        if self.capacity is None:
            raise ModeIncompatible(mode.value, "capacity")
        return self.capacity

    def validate(self, mode: BookingMode, *, index: int | None = None) -> BlockShape:
        """R14. Raises ``InvalidBlock`` naming the reason; ``index`` points into a request list."""
        length = self.minutes
        if length < MIN_BLOCK_MINUTES:
            raise InvalidBlock("a block lasts at least 15 minutes", index=index)
        if length > MAX_BLOCK_MINUTES:
            raise InvalidBlock(
                "a block lasts at most 12 hours (an end before the start means the next day)",
                index=index,
            )
        if self.slot_minutes is not None:
            if self.slot_minutes not in SLOT_MINUTES:
                raise InvalidBlock("the slot length is 5 to 120 minutes", index=index)
            if length % self.slot_minutes:
                raise InvalidBlock("the slot length must divide the block evenly", index=index)
        if self.capacity is not None and self.capacity not in CAPACITY:
            raise InvalidBlock("the capacity is 1 to 500", index=index)
        if mode is BookingMode.SLOTS and self.slot_minutes is None:
            raise InvalidBlock("slot booking needs a slot length", index=index)
        if mode is BookingMode.TOKENS and self.capacity is None:
            raise InvalidBlock("token booking needs a capacity", index=index)
        return self

    def supports(self, mode: BookingMode) -> bool:
        return (self.slot_minutes if mode is BookingMode.SLOTS else self.capacity) is not None


@dataclass(frozen=True, slots=True)
class WeekInterval:
    """A block on the circle of the week: ``start`` minutes after Monday 00:00, ``minutes`` long."""

    start: int
    minutes: int

    @classmethod
    def of(cls, weekday: int, shape: BlockShape) -> WeekInterval:
        return cls(
            weekday * MINUTES_PER_DAY + _minute_of_day(shape.start_time, "start_time"),
            shape.minutes,
        )

    def overlaps(self, other: WeekInterval) -> bool:
        return (other.start - self.start) % MINUTES_PER_WEEK < self.minutes or (
            self.start - other.start
        ) % MINUTES_PER_WEEK < other.minutes


def check_no_overlap(intervals: Sequence[WeekInterval]) -> None:
    """R15: raises ``ScheduleOverlap`` naming the first pair (indexes into ``intervals``)."""
    for i, first in enumerate(intervals):
        for j in range(i + 1, len(intervals)):
            if first.overlaps(intervals[j]):
                raise ScheduleOverlap(first=i, second=j)


def validate_weekday(weekday: int) -> int:
    if weekday not in range(7):
        raise InvalidValue("weekday", "must be 0 (Monday) to 6 (Sunday)")
    return weekday


@dataclass(slots=True)
class WeeklyBlock:
    """A weekly block of one doctor. Build with ``WeeklyBlock.create``; the constructor rehydrates.

    ``valid_from``/``valid_to`` (clinic-local dates, inclusive) keep history: replacing a schedule
    closes the blocks in force instead of deleting them (R16).
    """

    id: UUID
    clinic_id: UUID
    doctor_id: UUID
    weekday: int
    shape: BlockShape
    valid_from: date
    valid_to: date | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        doctor_id: UUID,
        weekday: int,
        shape: BlockShape,
        mode: BookingMode,
        valid_from: date,
        now: datetime,
        index: int | None = None,
    ) -> WeeklyBlock:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            weekday=validate_weekday(weekday),
            shape=shape.validate(mode, index=index),
            valid_from=valid_from,
            valid_to=None,
            created_at=now,
            updated_at=now,
        )

    def valid_on(self, on_date: date) -> bool:
        return self.valid_from <= on_date and (self.valid_to is None or on_date <= self.valid_to)

    def applies_on(self, on_date: date) -> bool:
        return self.valid_on(on_date) and on_date.weekday() == self.weekday

    def close(self, *, last_day: date, now: datetime) -> None:
        """Stop the block after ``last_day``; its earlier sessions keep their history."""
        if last_day < self.valid_from:
            raise InvalidValue("valid_to", "cannot end before the block starts")
        self.updated_at = require_utc(now, "now")
        self.valid_to = last_day

    @property
    def interval(self) -> WeekInterval:
        return WeekInterval.of(self.weekday, self.shape)
