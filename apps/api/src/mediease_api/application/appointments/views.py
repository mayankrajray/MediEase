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
class SessionView:
    """A session with the start of every slot an active appointment holds (slot mode)."""

    session: Session
    taken_slots: frozenset[datetime]
