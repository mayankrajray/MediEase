"""Domain events (M6a-P7, ADR-0017; FR-NTF-02, FR-NTF-04).

A feature publishes one of these in the transaction of the change it describes. An event names
what happened by IDs only: the notification service reads what it needs, in the same transaction,
so it always sees the change as committed. Nothing clinical is ever part of an event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AppointmentBooked:
    appointment_id: UUID


@dataclass(frozen=True, slots=True)
class AppointmentRescheduled:
    """``appointment_id`` is the new booking; ``from_appointment_id`` the one it replaced."""

    appointment_id: UUID
    from_appointment_id: UUID


@dataclass(frozen=True, slots=True)
class AppointmentCancelled:
    appointment_id: UUID


@dataclass(frozen=True, slots=True)
class PatientArrived:
    appointment_id: UUID


@dataclass(frozen=True, slots=True)
class PrescriptionIssued:
    prescription_id: UUID


@dataclass(frozen=True, slots=True)
class MessageFailed:
    message_id: UUID
    patient_id: UUID


@dataclass(frozen=True, slots=True)
class StaffJoined:
    membership_id: UUID


@dataclass(frozen=True, slots=True)
class BookingsToMove:
    """M6a-P8 (FR-APT-09): a schedule change closed sessions with live bookings.

    `change_id` names the change (the leave, or a fresh ID for a weekly schedule change) and keys
    the notification; `on_date` is the leave's day, or None for a weekly schedule change.
    """

    doctor_id: UUID
    change_id: UUID
    on_date: date | None


Event = (
    AppointmentBooked
    | AppointmentRescheduled
    | AppointmentCancelled
    | PatientArrived
    | PrescriptionIssued
    | MessageFailed
    | StaffJoined
    | BookingsToMove
)
