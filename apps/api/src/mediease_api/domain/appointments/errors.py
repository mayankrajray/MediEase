"""Booking errors (docs/ERRORS.md "Appointments and queue"). No names or reasons in details."""

from __future__ import annotations

from uuid import UUID

from mediease_api.domain.shared.errors import DomainError


class SlotTaken(DomainError):
    """R3, FR-APT-04: another active appointment holds this slot."""

    code = "APT_SLOT_TAKEN"

    def __init__(self) -> None:
        super().__init__("That slot was just booked.")


class SessionFull(DomainError):
    """R5, FR-APT-04: the session has no places left."""

    code = "APT_SESSION_FULL"

    def __init__(self) -> None:
        super().__init__("This session is full.")


class SessionClosed(DomainError):
    """R6, D10: the session no longer takes bookings (leave, a changed block, inactive doctor)."""

    code = "APT_SESSION_CLOSED"

    def __init__(self) -> None:
        super().__init__("The doctor is not available then.")


class OutsideSchedule(DomainError):
    """R6: the requested slot is not one of the session's slots."""

    code = "APT_OUTSIDE_SCHEDULE"

    def __init__(self) -> None:
        super().__init__("That time is outside the doctor's hours.")


class InPast(DomainError):
    """R6, D12: the session (token mode) or slot (slot mode) has already ended."""

    code = "APT_IN_PAST"

    def __init__(self) -> None:
        super().__init__("That time has already passed.")


class NotModifiable(DomainError):
    """D14, D15: the appointment's status or its session's end forbids the change."""

    code = "APT_NOT_MODIFIABLE"

    def __init__(self, status: str, action: str) -> None:
        super().__init__(f"This appointment cannot be {action} now.", status=status, action=action)


class AlreadyBooked(DomainError):
    """D13: the patient already has an active appointment in this session."""

    code = "APT_ALREADY_BOOKED"

    def __init__(self, appointment_id: UUID) -> None:
        super().__init__(
            "This patient is already booked in this session.",
            appointment_id=str(appointment_id),
        )
        self.appointment_id = appointment_id


class InvalidQueueTransition(DomainError):
    """R9, AC3, D18: not allowed from the current status, or the screen saw another status."""

    code = "QUE_INVALID_TRANSITION"

    def __init__(self, current: str, to: str) -> None:
        super().__init__("That status change isn't allowed.", **{"from": current, "to": to})


class WrongTime(DomainError):
    """D19: not the session's day (``not_today``), or a no-show too early (``not_started``)."""

    code = "QUE_WRONG_TIME"

    def __init__(self, reason: str) -> None:
        super().__init__("The queue can't be changed for that time now.", reason=reason)


class NoSession(DomainError):
    """D21: the doctor has no open session left today for a walk-in."""

    code = "QUE_NO_SESSION"

    def __init__(self) -> None:
        super().__init__("The doctor has no session left today.")
