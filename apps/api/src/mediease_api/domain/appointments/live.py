"""The live queue position behind a token link (M6b-P6; FR-QUE-06; portal spec R70; ADR-0019).

Computed on every read from the session's appointments. ``ahead`` counts **only** BOOKED and
ARRIVED entries before this one in queue order (token, else slot): a cancelled, completed or
no-show entry never counts. ``now_seeing`` is the IN_CONSULTATION entry's token or slot. Nothing
about any other patient leaves this module but those two numbers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.scheduling.sessions import Session

WAITING_STATUSES = frozenset({AppointmentStatus.BOOKED, AppointmentStatus.ARRIVED})


class LiveState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    WAITING = "WAITING"
    YOUR_TURN = "YOUR_TURN"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class LiveView:
    state: LiveState
    token_number: int | None
    slot_start: datetime | None
    ahead: int
    now_seeing_token: int | None
    now_seeing_slot: datetime | None


def _order(a: Appointment, session: Session) -> tuple[int, datetime]:
    return (a.token_number or 0, a.slot_start or session.starts_at)


def live_view(
    mine: Appointment, session: Session, appointments: Sequence[Appointment], now: datetime
) -> LiveView:
    """R70. ``appointments`` are the session's appointments (any status)."""
    me = _order(mine, session)
    ahead = sum(
        1
        for a in appointments
        if a.id != mine.id and a.status in WAITING_STATUSES and _order(a, session) < me
    )
    seeing = sorted(
        (a for a in appointments if a.status is AppointmentStatus.IN_CONSULTATION),
        key=lambda a: _order(a, session),
    )
    current = seeing[0] if seeing else None
    if mine.status is AppointmentStatus.CANCELLED:
        state = LiveState.CANCELLED
    elif mine.status in (AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW):
        state = LiveState.DONE
    elif mine.status is AppointmentStatus.IN_CONSULTATION:
        state = LiveState.YOUR_TURN
    elif now < session.starts_at and current is None:
        state = LiveState.NOT_STARTED
    else:
        state = LiveState.WAITING
    return LiveView(
        state=state,
        token_number=mine.token_number,
        slot_start=mine.slot_start,
        ahead=ahead if state is LiveState.WAITING or state is LiveState.NOT_STARTED else 0,
        now_seeing_token=current.token_number if current is not None else None,
        now_seeing_slot=current.slot_start if current is not None else None,
    )
