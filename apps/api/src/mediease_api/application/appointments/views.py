"""What the appointment use cases return. Domain entities; delivery formats them."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mediease_api.domain.appointments.appointment import Appointment, StatusChange
from mediease_api.domain.scheduling.sessions import Session


@dataclass(frozen=True, slots=True)
class AppointmentView:
    """An appointment with the session it is in (for its date and times)."""

    appointment: Appointment
    session: Session


@dataclass(frozen=True, slots=True)
class AppointmentDetail:
    view: AppointmentView
    history: tuple[StatusChange, ...]


@dataclass(frozen=True, slots=True)
class HeldPlace:
    """R23: one live hold on a session: its slot (None in token mode) and when it ends.
    The requester is not named here."""

    slot_start: datetime | None
    until: datetime


@dataclass(frozen=True, slots=True)
class SessionView:
    """A session with the start of every slot an active appointment holds (slot mode), and the
    places an online request holds for now (M6b-P4)."""

    session: Session
    taken_slots: frozenset[datetime]
    held: tuple[HeldPlace, ...] = ()
