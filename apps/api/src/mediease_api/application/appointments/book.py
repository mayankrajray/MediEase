"""Book an appointment (spec R3-R6; FR-APT-03, FR-APT-04, FR-APT-07; decisions D12, D13, D16).

Under the lock order of ``common.lock_sessions`` the session row is held ``FOR UPDATE``, so two
bookings in one session run one after the other and the second sees the first: capacity 1 and
two parallel requests give one 201 and one 409 (AC1). The appointment, the session's new
``booked_count`` and ``next_token``, the history row, the audit row and, when the patient allows
WhatsApp, the booking confirmation job commit together (R5; FR-APT-06 from M5-P2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.appointments.common import (
    ENTITY_TYPE,
    lock_sessions,
    place_metadata,
    record_history,
)
from mediease_api.application.appointments.views import AppointmentView
from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor
from mediease_api.application.notifications.service import publish
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.errors import SessionClosed
from mediease_api.domain.appointments.status import AppointmentSource
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.notifications.events import AppointmentBooked
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BookCommand:
    session_id: UUID
    patient_id: UUID
    slot_start: datetime | None = None
    source: AppointmentSource = AppointmentSource.FRONT_DESK
    reason: str | None = None


class BookAppointment:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, *, clinic_id: UUID, actor: Actor, cmd: BookCommand) -> AppointmentView:
        with self._uow as uow:
            tenant = uow.tenant(clinic_id)
            patient = tenant.patients.get(cmd.patient_id)
            if patient is None:
                logger.info(
                    "tenancy.not_found",
                    entity="patient",
                    entity_id=str(cmd.patient_id),
                    clinic_id=str(clinic_id),
                )
                raise NotFound("patient")
            locked = lock_sessions(tenant, clinic_id, [cmd.session_id])
            session = locked.sessions[cmd.session_id]
            if not locked.doctors[session.doctor_id].is_active:
                raise SessionClosed()

            now = self._clock.now()
            appointment = Appointment.book(
                session,
                id=self._ids.new_id(),
                patient_id=cmd.patient_id,
                active=tenant.appointments.list_active_for_sessions([session.id]),
                now=now,
                slot_start=cmd.slot_start,
                source=cmd.source,
                reason=cmd.reason,
                created_by=actor.user_id,
            )
            tenant.sessions.update(session)
            tenant.appointments.add(appointment)
            record_history(tenant, appointment, ids=self._ids, actor=actor, from_status=None)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.APPOINTMENT_BOOKED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=appointment.id,
                metadata=place_metadata(appointment, session),
            )
            # FR-APT-06 (M5-P2), through the notification service from M6a-P7 (ADR-0017): the
            # patient's confirmation and the doctor's notification commit with the booking.
            publish(
                uow,
                AppointmentBooked(appointment.id),
                clinic_id=clinic_id,
                ids=self._ids,
                now=now,
                request_id=actor.info.request_id,
                actor_user_id=actor.user_id,
            )
            uow.commit()

        logger.info(
            "appointment.booked",
            clinic_id=str(clinic_id),
            appointment_id=str(appointment.id),
            session_id=str(session.id),
            mode=session.mode.value,
            source=appointment.source.value,
        )
        return AppointmentView(appointment, session)
