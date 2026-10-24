"""Reminder errors (docs/ERRORS.md "Reminders, messaging, webhooks, jobs")."""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError

# Recorded on a reminder that could not be sent because the clinic has no phone (decision 6A).
REM_CLINIC_PHONE_MISSING = "REM_CLINIC_PHONE_MISSING"
# M6a-P8: recorded on an appointment reminder cancelled by the system at send time, because the
# appointment is no longer booked or its session was closed (leave, a schedule change); or because
# it is now too late to remind before the visit.
REM_APPOINTMENT_CHANGED = "REM_APPOINTMENT_CHANGED"
REM_TOO_LATE = "REM_TOO_LATE"


class NoConsent(DomainError):
    code = "REM_NO_CONSENT"

    def __init__(self) -> None:
        super().__init__("This patient has not agreed to WhatsApp messages, or has opted out.")


class InPast(DomainError):
    code = "REM_IN_PAST"

    def __init__(self) -> None:
        super().__init__("The follow-up date must be after today.")


class ClinicPhoneMissing(DomainError):
    code = REM_CLINIC_PHONE_MISSING

    def __init__(self) -> None:
        super().__init__("Add the clinic's phone number before scheduling reminders.")


class NotScheduled(DomainError):
    code = "REM_NOT_SCHEDULED"

    def __init__(self, status: str) -> None:
        super().__init__(f"This reminder is {status} and can no longer be changed.", status=status)


class FollowsAppointment(DomainError):
    """M6a-P8 decision 4A: an appointment reminder moves with its appointment, never alone."""

    code = "REM_FOLLOWS_APPOINTMENT"

    def __init__(self) -> None:
        super().__init__("This reminder follows its appointment: move the appointment instead.")
