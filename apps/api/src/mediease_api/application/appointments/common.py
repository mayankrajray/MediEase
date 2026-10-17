"""Shared by the booking use cases: one lock order, history rows and audit metadata.

Lock order (design note "Concepts" 2, spec R20): every doctor involved ``FOR SHARE`` in ID
order — the lock session generation takes and a schedule change waits for — then every session
involved ``FOR UPDATE`` in ID order. A schedule change holds the doctor ``FOR UPDATE``, so it
never deletes or closes a session while a booking in it is under way, and two reschedules that
cross between the same two sessions cannot deadlock.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.context import Actor
from mediease_api.application.scheduling.schedules import load_doctor
from mediease_api.domain.appointments.appointment import Appointment, history_entry
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.ids import IdPort
from mediease_api.ports.repositories import RowLock
from mediease_api.ports.unit_of_work import TenantRepositories

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "appointment"


@dataclass(frozen=True, slots=True)
class Locked:
    doctors: dict[UUID, Doctor]
    sessions: dict[UUID, Session]


def lock_sessions(
    tenant: TenantRepositories, clinic_id: UUID, session_ids: Collection[UUID]
) -> Locked:
    """The sessions (and their doctors) locked in the one order; ``NotFound`` for a stranger's."""
    doctor_ids: set[UUID] = set()
    for session_id in session_ids:
        seen = tenant.sessions.get(session_id)
        if seen is None:
            logger.info(
                "tenancy.not_found",
                entity="session",
                entity_id=str(session_id),
                clinic_id=str(clinic_id),
            )
            raise NotFound("session")
        doctor_ids.add(seen.doctor_id)
    doctors = {
        doctor_id: load_doctor(tenant, clinic_id, doctor_id, lock=RowLock.SHARE)
        for doctor_id in sorted(doctor_ids)
    }
    sessions: dict[UUID, Session] = {}
    for session_id in sorted(set(session_ids)):
        locked = tenant.sessions.get(session_id, lock=RowLock.UPDATE)
        if locked is None:
            # A schedule change held the doctor and deleted the (unbooked) session while we
            # waited for the doctor lock: it is gone, so nothing was booked or lost (R20).
            logger.info("appointment.session_gone", session_id=str(session_id))
            raise NotFound("session")
        sessions[session_id] = locked
    return Locked(doctors, sessions)


def load_appointment(
    tenant: TenantRepositories, clinic_id: UUID, appointment_id: UUID, *, for_update: bool = False
) -> Appointment:
    appointment = tenant.appointments.get(appointment_id, for_update=for_update)
    if appointment is None:
        logger.info(
            "tenancy.not_found",
            entity="appointment",
            entity_id=str(appointment_id),
            clinic_id=str(clinic_id),
        )
        raise NotFound("appointment")
    return appointment


def record_history(
    tenant: TenantRepositories,
    appointment: Appointment,
    *,
    ids: IdPort,
    actor: Actor,
    from_status: AppointmentStatus | None,
) -> None:
    tenant.appointment_history.add(
        history_entry(
            appointment,
            id=ids.new_id(),
            from_status=from_status,
            changed_by=actor.user_id,
            request_id=actor.info.request_id,
        )
    )


def place_metadata(appointment: Appointment, session: Session) -> dict[str, str]:
    """IDs, mode and place for the audit row — never a name or the appointment's reason."""
    metadata = {
        "session_id": str(session.id),
        "doctor_id": str(session.doctor_id),
        "patient_id": str(appointment.patient_id),
        "mode": session.mode.value,
        "source": appointment.source.value,
    }
    if appointment.token_number is not None:
        metadata["token_number"] = str(appointment.token_number)
    if appointment.slot_start is not None:
        metadata["slot_start"] = appointment.slot_start.isoformat()
    return metadata
