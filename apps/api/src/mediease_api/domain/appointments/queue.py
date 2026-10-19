"""The daily queue: status transitions and walk-ins (spec R9-R11, AC3; decisions D18-D21).

``transition`` moves an appointment along the state machine of spec §3, but only from the status
the caller saw (D18), on the session's day (D19), and a no-show only once the session (token) or
slot (slot mode) has started. Entering a state sets its timestamp. Cancel is not here: it has its
own rules and route (R7, D14).

``first_free_slot`` is the slot a walk-in takes in slot mode: the earliest one that has not ended
and that no active appointment holds (no overbooking, D6). Pure: the caller passes ``now`` and the
clinic's ``today``.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime, timedelta

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.errors import InvalidQueueTransition, WrongTime
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.time import require_utc

S = AppointmentStatus

# Spec §3. CANCELLED is reached only through cancel (P2).
TRANSITIONS: dict[AppointmentStatus, frozenset[AppointmentStatus]] = {
    S.BOOKED: frozenset({S.ARRIVED, S.NO_SHOW}),
    S.ARRIVED: frozenset({S.IN_CONSULTATION, S.NO_SHOW}),
    S.IN_CONSULTATION: frozenset({S.COMPLETED}),
    S.NO_SHOW: frozenset({S.ARRIVED}),  # a late arrival, the same day only (D19)
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
}


def is_session_day(session: Session, *, now: datetime, today: date) -> bool:
    """D19: the session's clinic-local date, or while an overnight session is still running."""
    return session.on_date == today or session.starts_at <= now < session.ends_at


def transition(
    appointment: Appointment,
    session: Session,
    *,
    seen: AppointmentStatus,
    to: AppointmentStatus,
    now: datetime,
    today: date,
) -> AppointmentStatus:
    """R9: apply ``seen -> to`` to the appointment in its locked session; returns the old status."""
    now = require_utc(now, "now")
    assert appointment.session_id == session.id, "the appointment's own session"
    current = appointment.status
    if seen is not current or to not in TRANSITIONS[current]:
        # A stale screen (D18) gets the real status, so it can refresh and decide again.
        raise InvalidQueueTransition(current.value, to.value)
    if not is_session_day(session, now=now, today=today):
        raise WrongTime("not_today")
    if to is S.NO_SHOW:
        started = appointment.slot_start if session.mode is BookingMode.SLOTS else None
        if now < (started or session.starts_at):
            raise WrongTime("not_started")

    appointment.status = to
    if to is S.ARRIVED:
        appointment.arrived_at = now
    elif to is S.IN_CONSULTATION:
        appointment.started_at = now
    elif to is S.COMPLETED:
        appointment.completed_at = now
    appointment.updated_at = now
    return current


# Spec R10: a booking still BOOKED this long after its session ended becomes NO_SHOW (M5-P4).
NO_SHOW_AFTER = timedelta(minutes=60)


def no_show_cutoff(now: datetime) -> datetime:
    """Sessions that ended at or before this instant have overdue bookings."""
    return require_utc(now, "now") - NO_SHOW_AFTER


def mark_no_show_automatically(
    appointment: Appointment, session: Session, *, now: datetime
) -> bool:
    """R10: ``BOOKED`` an hour past the session's end becomes ``NO_SHOW``; False otherwise.

    Not ``transition``: that is bound to the session's day (D19), and a late session's hour can
    end after midnight. A late arrival can still move it to ``ARRIVED`` the same day (D19).
    """
    now = require_utc(now, "now")
    assert appointment.session_id == session.id, "the appointment's own session"
    if appointment.status is not S.BOOKED or session.ends_at > no_show_cutoff(now):
        return False
    appointment.status = S.NO_SHOW
    appointment.updated_at = now
    return True


def first_free_slot(
    session: Session, *, taken: Collection[datetime], now: datetime
) -> datetime | None:
    """R11, D6: the earliest slot that has not ended and is free; None when there is none."""
    return next((start for start, end in session.slots() if end > now and start not in taken), None)


def wait_minutes(appointment: Appointment, now: datetime) -> int | None:
    """Minutes since arrival while waiting; arrival to start once the consultation began."""
    if appointment.arrived_at is None:
        return None
    if appointment.status is S.ARRIVED:
        until = now
    elif appointment.status in (S.IN_CONSULTATION, S.COMPLETED) and appointment.started_at:
        until = appointment.started_at
    else:
        return None
    return max(0, int((until - appointment.arrived_at).total_seconds() // 60))
