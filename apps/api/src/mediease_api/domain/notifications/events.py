"""Domain events (M6a-P7, ADR-0017; FR-NTF-02, FR-NTF-04).

A feature publishes one of these in the transaction of the change it describes. An event names
what happened by IDs only: the notification service reads what it needs, in the same transaction,
so it always sees the change as committed. Nothing clinical is ever part of an event.
"""

from __future__ import annotations

from dataclasses import dataclass
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


Event = (
    AppointmentBooked
    | AppointmentRescheduled
    | AppointmentCancelled
    | PatientArrived
    | PrescriptionIssued
    | MessageFailed
    | StaffJoined
)
