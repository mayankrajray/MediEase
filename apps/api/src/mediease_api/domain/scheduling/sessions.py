"""Sessions: one doctor's bookable block on one clinic-local date (spec R1-R4, R16-R18; AC5).

Planning is pure: given the rules (weekly blocks and that date's exceptions), the clinic's zone
and booking mode, ``plan_day`` says which sessions a date should have, in UTC. A session belongs to
the date it starts on, even when it runs past midnight (R2). Generation inserts the planned
sessions that do not exist yet; after a change, ``reconcile`` compares what exists with the new
plan and never touches a session that has bookings (decision D4).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock
from mediease_api.domain.scheduling.exceptions import ExceptionKind, ScheduleException
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.time import require_utc

# Sessions are generated from the clinic's today up to this many days ahead (R1).
GENERATION_HORIZON_DAYS = 180


class SessionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class PlannedSession:
    """What the rules say a date should have. ``key`` is the database's uniqueness."""

    doctor_id: UUID
    on_date: date
    starts_at: datetime
    ends_at: datetime
    mode: BookingMode
    slot_minutes: int | None
    capacity: int

    @property
    def key(self) -> tuple[UUID, datetime]:
        return (self.doctor_id, self.starts_at)


@dataclass(slots=True)
class Session:
    """A materialised session; ``booked_count`` and ``next_token`` are kept under a lock (P2)."""

    id: UUID
    clinic_id: UUID
    doctor_id: UUID
    on_date: date
    starts_at: datetime
    ends_at: datetime
    mode: BookingMode
    slot_minutes: int | None
    capacity: int
    booked_count: int
    next_token: int
    status: SessionStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_plan(
        cls, plan: PlannedSession, *, id: UUID, clinic_id: UUID, now: datetime
    ) -> Session:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            doctor_id=plan.doctor_id,
            on_date=plan.on_date,
            starts_at=plan.starts_at,
            ends_at=plan.ends_at,
            mode=plan.mode,
            slot_minutes=plan.slot_minutes,
            capacity=plan.capacity,
            booked_count=0,
            next_token=1,
            status=SessionStatus.OPEN,
            created_at=now,
            updated_at=now,
        )

    @property
    def key(self) -> tuple[UUID, datetime]:
        return (self.doctor_id, self.starts_at)

    @property
    def available(self) -> int:
        return self.capacity - self.booked_count

    def matches(self, plan: PlannedSession) -> bool:
        return (
            self.key == plan.key
            and self.ends_at == plan.ends_at
            and self.mode is plan.mode
            and self.slot_minutes == plan.slot_minutes
            and self.capacity == plan.capacity
        )

    def slots(self) -> list[tuple[datetime, datetime]]:
        """Slot mode: ``[starts_at, ends_at)`` by the slot length (R3); empty in token mode."""
        if self.mode is not BookingMode.SLOTS or self.slot_minutes is None:
            return []
        step = timedelta(minutes=self.slot_minutes)
        count = int((self.ends_at - self.starts_at) / step)
        return [(self.starts_at + step * i, self.starts_at + step * (i + 1)) for i in range(count)]


def session_bounds(on_date: date, shape: BlockShape, timezone: str) -> tuple[datetime, datetime]:
    """The block on ``on_date`` in the clinic's zone, as UTC instants (R2; AC5)."""
    zone = ZoneInfo(timezone)
    starts = datetime.combine(on_date, shape.start_time, tzinfo=zone)
    end_date = on_date + timedelta(days=1) if shape.overnight else on_date
    ends = datetime.combine(end_date, shape.end_time, tzinfo=zone)
    return starts.astimezone(UTC), ends.astimezone(UTC)


def plan_day(
    *,
    doctor_id: UUID,
    on_date: date,
    timezone: str,
    mode: BookingMode,
    blocks: Iterable[WeeklyBlock],
    exceptions: Iterable[ScheduleException],
) -> list[PlannedSession]:
    """R1: the date's blocks unless the doctor is on leave, plus that date's extra sessions."""
    todays = [e for e in exceptions if e.doctor_id == doctor_id and e.on_date == on_date]
    on_leave = any(e.kind is ExceptionKind.LEAVE for e in todays)
    shapes = (
        []
        if on_leave
        else [b.shape for b in blocks if b.doctor_id == doctor_id and b.applies_on(on_date)]
    )
    shapes += [e.shape for e in todays if e.kind is ExceptionKind.EXTRA and e.shape is not None]

    planned: dict[datetime, PlannedSession] = {}
    for shape in shapes:
        starts, ends = session_bounds(on_date, shape, timezone)
        planned.setdefault(
            starts,
            PlannedSession(
                doctor_id=doctor_id,
                on_date=on_date,
                starts_at=starts,
                ends_at=ends,
                mode=mode,
                slot_minutes=shape.slot_minutes if mode is BookingMode.SLOTS else None,
                capacity=shape.capacity_for(mode),
            ),
        )
    return sorted(planned.values(), key=lambda p: p.starts_at)


def overlaps(first: tuple[datetime, datetime], second: tuple[datetime, datetime]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """What a change means for existing sessions (D4): delete the unbooked, keep the booked."""

    to_delete: tuple[Session, ...]
    kept: tuple[Session, ...]


def reconcile(existing: Sequence[Session], planned: Sequence[PlannedSession]) -> Reconciliation:
    """Compare a date's sessions with its new plan. Missing ones are left for generation (R1)."""
    plan_by_key = {p.key: p for p in planned}
    to_delete: list[Session] = []
    kept: list[Session] = []
    for session in existing:
        plan = plan_by_key.get(session.key)
        if plan is not None and session.matches(plan):
            continue
        (kept if session.booked_count > 0 else to_delete).append(session)
    return Reconciliation(tuple(to_delete), tuple(kept))


def horizon(today: date) -> date:
    return today + timedelta(days=GENERATION_HORIZON_DAYS)
