"""Sessions: one doctor's bookable block on one clinic-local date (spec R1-R4, R16-R18; AC5).

Planning is pure: given the rules (weekly blocks and that date's exceptions), the clinic's zone
and booking mode, ``plan_day`` says which sessions a date should have, in UTC. A session belongs to
the date it starts on, even when it runs past midnight (R2). Generation inserts the planned
sessions that do not exist yet; after a change, ``reconcile`` compares what exists with the new
plan and never deletes a session that has bookings (decision D4). A booked session that no longer
matches is closed to new bookings (D10), or resized in place when only its capacity changed (D11).

Statuses: ``OPEN`` takes bookings; ``CLOSED`` keeps its bookings but takes no new ones;
``CANCELLED`` is retired: no longer planned and unbooked, kept only because cancelled appointments
point at it, and invisible to listing and generation (M3-P2).
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
    # Kept for its bookings, closed to new ones (D10).
    CLOSED = "CLOSED"
    # Retired: no longer planned and unbooked, but cancelled appointments still refer to it.
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

    @property
    def is_open(self) -> bool:
        return self.status is SessionStatus.OPEN

    def take_place(self, now: datetime) -> int | None:
        """One more booking (R4, R5); the token in token mode. The caller checked capacity."""
        assert self.booked_count < self.capacity, "checked by the booking rules"
        token: int | None = None
        if self.mode is BookingMode.TOKENS:
            # Never reused, including after a cancellation (R4, AC2).
            token = self.next_token
            self.next_token += 1
        self.booked_count += 1
        self.updated_at = require_utc(now, "now")
        return token

    def release(self, now: datetime) -> None:
        """A booking left (cancel, reschedule): its place is free again, its token is not (R7)."""
        assert self.booked_count > 0, "only a booked session is released"
        self.booked_count -= 1
        self.updated_at = require_utc(now, "now")

    def close(self, now: datetime) -> None:
        """D10: keep the bookings, take no new ones."""
        self.status = SessionStatus.CLOSED
        self.updated_at = require_utc(now, "now")

    def reopen(self, now: datetime) -> None:
        """The rules plan this session again as it is."""
        self.status = SessionStatus.OPEN
        self.updated_at = require_utc(now, "now")

    def retire(self, now: datetime) -> None:
        """No longer planned and unbooked, but kept for the appointments that point at it."""
        assert self.booked_count == 0, "a booked session is closed, never retired"
        self.status = SessionStatus.CANCELLED
        self.updated_at = require_utc(now, "now")

    def resize(self, capacity: int, now: datetime) -> None:
        """D11: only the capacity changed and the bookings fit; open for the new places."""
        assert capacity >= self.booked_count, "checked by reconcile"
        self.capacity = capacity
        self.status = SessionStatus.OPEN
        self.updated_at = require_utc(now, "now")

    def revive(self, plan: PlannedSession, now: datetime) -> None:
        """A retired session planned again: it takes the plan's shape and opens.

        The row is reused because ``UNIQUE (doctor_id, starts_at)`` would refuse a second one;
        ``next_token`` carries on, so a token is still never handed out twice in one session.
        """
        assert self.status is SessionStatus.CANCELLED and self.booked_count == 0
        assert plan.key == self.key
        self.ends_at = plan.ends_at
        self.mode = plan.mode
        self.slot_minutes = plan.slot_minutes
        self.capacity = plan.capacity
        self.status = SessionStatus.OPEN
        self.updated_at = require_utc(now, "now")

    def only_capacity_differs(self, plan: PlannedSession) -> bool:
        """D11: the same session in every way but its capacity, and its bookings still fit."""
        return (
            self.key == plan.key
            and self.ends_at == plan.ends_at
            and self.mode is plan.mode
            and self.slot_minutes == plan.slot_minutes
            and self.capacity != plan.capacity
            and plan.capacity >= self.booked_count
        )

    def slot_at(self, start: datetime) -> tuple[datetime, datetime] | None:
        """The slot starting at ``start``, or None when it is not on the session's grid (R3)."""
        return next((slot for slot in self.slots() if slot[0] == start), None)

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
    """What a change means for a date's existing sessions (D4, D10, D11).

    ``to_delete``: unbooked and no longer planned as they are (removed; the next read generates
    the plan). ``to_close``: booked, no longer planned, still open. ``to_reopen``: closed but
    planned again exactly. ``to_resize``: booked, only the capacity changed, the bookings fit.
    ``kept``: every booked session that is closed after the change, for the owner to move.
    """

    to_delete: tuple[Session, ...]
    kept: tuple[Session, ...]
    to_close: tuple[Session, ...] = ()
    to_reopen: tuple[Session, ...] = ()
    to_resize: tuple[tuple[Session, int], ...] = ()


def reconcile(existing: Sequence[Session], planned: Sequence[PlannedSession]) -> Reconciliation:
    """Compare a date's sessions with its new plan. Missing ones are left for generation (R1)."""
    plan_by_key = {p.key: p for p in planned}
    to_delete: list[Session] = []
    kept: list[Session] = []
    to_close: list[Session] = []
    to_reopen: list[Session] = []
    to_resize: list[tuple[Session, int]] = []
    for session in existing:
        if session.status is SessionStatus.CANCELLED:
            continue  # retired: generation revives it if the rules plan it again
        plan = plan_by_key.get(session.key)
        if plan is not None and session.matches(plan):
            if session.status is SessionStatus.CLOSED:
                to_reopen.append(session)
        elif session.booked_count == 0:
            to_delete.append(session)
        elif plan is not None and session.only_capacity_differs(plan):
            to_resize.append((session, plan.capacity))
        else:
            if session.status is SessionStatus.OPEN:
                to_close.append(session)
            kept.append(session)
    return Reconciliation(
        to_delete=tuple(to_delete),
        kept=tuple(kept),
        to_close=tuple(to_close),
        to_reopen=tuple(to_reopen),
        to_resize=tuple(to_resize),
    )


def horizon(today: date) -> date:
    return today + timedelta(days=GENERATION_HORIZON_DAYS)
