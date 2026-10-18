"""Reschedule an appointment (spec R8; FR-APT-05; decision D15).

A cancel with ``RESCHEDULED`` and a new booking that points at the old appointment, in one
transaction: either both happen or neither. From ``BOOKED`` only, to any open session of the
clinic — another doctor's, or another slot of the same session. The source carries over, and the
old session may be ``CLOSED`` (that is how bookings leave a session closed by leave, D10). Both
sessions and their doctors are locked in the one order, so crossing reschedules cannot deadlock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.appointments.common import (
    ENTITY_TYPE,
    load_appointment,
    lock_sessions,
    place_metadata,
    record_history,
)
from mediease_api.application.appointments.views import AppointmentView
from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor
from mediease_api.application.messaging.booking import enqueue_booking_confirmation
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.errors import NotModifiable, SessionClosed
from mediease_api.domain.appointments.status import AppointmentStatus, CancelReason
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RescheduleCommand:
    session_id: UUID
    slot_start: datetime | None = None


class RescheduleAppointment:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, *, clinic_id: UUID, actor: Actor, appointment_id: UUID, cmd: RescheduleCommand
    ) -> AppointmentView:
        with self._uow as uow:
            tenant = uow.tenant(clinic_id)
            seen = load_appointment(tenant, clinic_id, appointment_id)
            locked = lock_sessions(tenant, clinic_id, {seen.session_id, cmd.session_id})
            old = load_appointment(tenant, clinic_id, appointment_id, for_update=True)
            source, target = locked.sessions[old.session_id], locked.sessions[cmd.session_id]
            if old.status is not AppointmentStatus.BOOKED:
                raise NotModifiable(old.status.value, "rescheduled")  # D15
            if old.is_same_place(target, cmd.slot_start):
                raise InvalidValue("session_id", "is where the appointment already is")
            if not locked.doctors[target.doctor_id].is_active:
                raise SessionClosed()

            now = self._clock.now()
            old.cancel(source, reason=CancelReason.RESCHEDULED, now=now)
            tenant.appointments.update(old)
            new = Appointment.book(
                target,
                id=self._ids.new_id(),
                patient_id=old.patient_id,
                active=tenant.appointments.list_active_for_sessions([target.id]),
                now=now,
                slot_start=cmd.slot_start,
                source=old.source,
                reason=old.reason,
                created_by=actor.user_id,
                rescheduled_from_id=old.id,
            )
            tenant.sessions.update(source)
            if target is not source:
                tenant.sessions.update(target)
            tenant.appointments.add(new)
            record_history(
                tenant, old, ids=self._ids, actor=actor, from_status=AppointmentStatus.BOOKED
            )
            record_history(tenant, new, ids=self._ids, actor=actor, from_status=None)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.APPOINTMENT_RESCHEDULED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=new.id,
                metadata={
                    **place_metadata(new, target),
                    "rescheduled_from_id": str(old.id),
                    "from_session_id": str(source.id),
                },
            )
            patient = tenant.patients.get(new.patient_id)
            assert patient is not None  # a foreign key keeps it
            # FR-APT-06 (M5-P2, decision 6A): the new time is confirmed; the old job, if still
            # queued, finds its appointment cancelled and sends nothing.
            enqueue_booking_confirmation(
                uow,
                ids=self._ids,
                appointment=new,
                patient=patient,
                request_id=actor.info.request_id,
                now=now,
            )
            uow.commit()

        logger.info(
            "appointment.rescheduled",
            clinic_id=str(clinic_id),
            appointment_id=str(new.id),
            rescheduled_from_id=str(old.id),
        )
        return AppointmentView(new, target)
