"""An appointment: one patient's place in one session (spec R3-R8; decisions D12-D15).

Booking is a rule about the session as it is under its row lock: the caller loads the session
``FOR UPDATE`` and the session's active appointments, and ``Appointment.book`` decides. It takes
the place on the session itself (``booked_count``, and the next token in token mode), so the two
rows the caller writes back always agree. Cancelling releases the place but never the token (R4,
R7). A reschedule is a cancel with ``RESCHEDULED`` plus a new booking that points at the old one
(R8). Every status change is a ``StatusChange`` row (FR-APT-05: history is retained).

The domain never reads a clock: ``now`` is passed in, in UTC.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mediease_api.domain.appointments.errors import (
    AlreadyBooked,
    InPast,
    NotModifiable,
    OutsideSchedule,
    SessionClosed,
    SessionFull,
    SlotTaken,
)
from mediease_api.domain.appointments.status import (
    ACTIVE_STATUSES,
    AppointmentSource,
    AppointmentStatus,
    CancelReason,
)
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

# A short, non-clinical note ("follow-up"); never logged, audited or messaged.
REASON_MAX = 120
CANCEL_NOTE_MAX = 200


@dataclass(frozen=True, slots=True)
class StatusChange:
    """One row of an appointment's history (``appointment_status_history``, append-only)."""

    id: UUID
    clinic_id: UUID
    appointment_id: UUID
    from_status: AppointmentStatus | None
    to_status: AppointmentStatus
    changed_by: UUID | None
    changed_at: datetime
    request_id: str | None


@dataclass(slots=True)
class Appointment:
    id: UUID
    clinic_id: UUID
    session_id: UUID
    doctor_id: UUID
    patient_id: UUID
    slot_start: datetime | None
    token_number: int | None
    status: AppointmentStatus
    source: AppointmentSource
    reason: str | None
    cancel_reason: CancelReason | None
    cancel_note: str | None
    cancelled_at: datetime | None
    rescheduled_from_id: UUID | None
    arrived_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @classmethod
    def book(
        cls,
        session: Session,
        *,
        id: UUID,
        patient_id: UUID,
        active: Iterable[Appointment],
        now: datetime,
        slot_start: datetime | None = None,
        source: AppointmentSource = AppointmentSource.FRONT_DESK,
        reason: str | None = None,
        created_by: UUID | None = None,
        rescheduled_from_id: UUID | None = None,
    ) -> Appointment:
        """R5, R6: a place in ``session`` for the patient, taken on the session in place.

        ``active`` are the session's active appointments, read under the session's row lock.
        Checks, in order: open session; the slot or token rule of the session's mode; not over
        (D12); the patient not already booked (D13); the slot free (R3); a place left (R5).
        """
        now = require_utc(now, "now")
        if not session.is_open:
            raise SessionClosed()
        reason = _optional_text(reason, "reason", REASON_MAX)

        if session.mode is BookingMode.SLOTS:
            if slot_start is None:
                raise InvalidValue("slot_start", "is required in slot mode")
            slot = session.slot_at(require_utc(slot_start, "slot_start"))
            if slot is None:
                raise OutsideSchedule()
            if now >= slot[1]:
                raise InPast()
        else:
            if slot_start is not None:
                raise InvalidValue("slot_start", "is not used in token mode")
            if now >= session.ends_at:
                raise InPast()

        active = [a for a in active if a.is_active]
        mine = next((a for a in active if a.patient_id == patient_id), None)
        if mine is not None:
            raise AlreadyBooked(mine.id)
        if slot_start is not None and any(a.slot_start == slot_start for a in active):
            raise SlotTaken()
        if session.available <= 0:
            raise SessionFull()

        token = session.take_place(now)
        return cls(
            id=id,
            clinic_id=session.clinic_id,
            session_id=session.id,
            doctor_id=session.doctor_id,
            patient_id=patient_id,
            slot_start=slot_start,
            token_number=token,
            status=AppointmentStatus.BOOKED,
            source=source,
            reason=reason,
            cancel_reason=None,
            cancel_note=None,
            cancelled_at=None,
            rescheduled_from_id=rescheduled_from_id,
            arrived_at=None,
            started_at=None,
            completed_at=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    def cancel(
        self,
        session: Session,
        *,
        reason: CancelReason,
        now: datetime,
        note: str | None = None,
    ) -> None:
        """R7, D14: from BOOKED or ARRIVED until the session ends; frees the place, not the token.

        After the session has ended the right outcome is NO_SHOW (P3), so cancel is refused.
        """
        now = require_utc(now, "now")
        self._check_session(session)
        allowed = {AppointmentStatus.BOOKED, AppointmentStatus.ARRIVED}
        if reason is CancelReason.RESCHEDULED:
            allowed = {AppointmentStatus.BOOKED}  # D15
        action = "rescheduled" if reason is CancelReason.RESCHEDULED else "cancelled"
        if self.status not in allowed or now >= session.ends_at:
            raise NotModifiable(self.status.value, action)
        note = _optional_text(note, "note", CANCEL_NOTE_MAX)
        if reason is CancelReason.OTHER and note is None:
            raise InvalidValue("note", "is required when the reason is OTHER")

        self.status = AppointmentStatus.CANCELLED
        self.cancel_reason = reason
        self.cancel_note = note
        self.cancelled_at = now
        self.updated_at = now
        session.release(now)

    def is_same_place(self, session: Session, slot_start: datetime | None) -> bool:
        """A reschedule to where the appointment already is (same token session or slot)."""
        if session.id != self.session_id:
            return False
        return session.mode is BookingMode.TOKENS or slot_start == self.slot_start

    def _check_session(self, session: Session) -> None:
        assert session.id == self.session_id, "the appointment's own session, locked"


def history_entry(
    appointment: Appointment,
    *,
    id: UUID,
    from_status: AppointmentStatus | None,
    changed_by: UUID | None,
    request_id: str | None,
) -> StatusChange:
    """The history row for the appointment's change into its current status."""
    return StatusChange(
        id=id,
        clinic_id=appointment.clinic_id,
        appointment_id=appointment.id,
        from_status=from_status,
        to_status=appointment.status,
        changed_by=changed_by,
        changed_at=appointment.updated_at,
        request_id=request_id,
    )


def _optional_text(value: str | None, field: str, limit: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > limit:
        raise InvalidValue(field, f"must be at most {limit} characters")
    return value
