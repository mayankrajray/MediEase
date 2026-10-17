"""The values an appointment carries (spec §3 state machine, FR-APT-07, decision D14)."""

from __future__ import annotations

from enum import StrEnum


class AppointmentStatus(StrEnum):
    BOOKED = "BOOKED"
    ARRIVED = "ARRIVED"
    IN_CONSULTATION = "IN_CONSULTATION"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"


# Every status but CANCELLED holds a place in its session (slot, token and booked_count).
ACTIVE_STATUSES = frozenset(AppointmentStatus) - {AppointmentStatus.CANCELLED}


class AppointmentSource(StrEnum):
    """Where the booking came from (FR-APT-07)."""

    FRONT_DESK = "FRONT_DESK"
    PHONE = "PHONE"
    WHATSAPP = "WHATSAPP"
    PUBLIC_PAGE = "PUBLIC_PAGE"
    WALK_IN = "WALK_IN"


# What staff may choose when booking: WALK_IN has its own route (P3), PUBLIC_PAGE its own page.
STAFF_SOURCES = frozenset(
    {AppointmentSource.FRONT_DESK, AppointmentSource.PHONE, AppointmentSource.WHATSAPP}
)


class CancelReason(StrEnum):
    """Why an appointment was cancelled (D14). RESCHEDULED is set by a reschedule only."""

    PATIENT_REQUEST = "PATIENT_REQUEST"
    CLINIC_REQUEST = "CLINIC_REQUEST"
    DOCTOR_UNAVAILABLE = "DOCTOR_UNAVAILABLE"
    DUPLICATE = "DUPLICATE"
    OTHER = "OTHER"
    RESCHEDULED = "RESCHEDULED"


STAFF_CANCEL_REASONS = frozenset(CancelReason) - {CancelReason.RESCHEDULED}
