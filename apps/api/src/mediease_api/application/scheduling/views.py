"""What the scheduling use cases return. Domain entities; delivery formats them."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from mediease_api.domain.scheduling.blocks import WeeklyBlock
from mediease_api.domain.scheduling.exceptions import ScheduleException
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session


@dataclass(frozen=True, slots=True)
class ScheduleView:
    """A doctor's blocks in force from the clinic's today, and their upcoming exceptions."""

    doctor_id: UUID
    booking_mode: BookingMode
    blocks: tuple[WeeklyBlock, ...]
    exceptions: tuple[ScheduleException, ...]


@dataclass(frozen=True, slots=True)
class ScheduleChange:
    """After a change: the schedule now, and booked sessions the change did not touch (D4)."""

    schedule: ScheduleView
    kept_sessions: tuple[Session, ...]


@dataclass(frozen=True, slots=True)
class ExceptionChange:
    exception: ScheduleException
    kept_sessions: tuple[Session, ...]
