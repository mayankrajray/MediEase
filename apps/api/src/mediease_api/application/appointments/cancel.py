"""Cancel an appointment (spec R7; FR-APT-05; decision D14).

From ``BOOKED`` or ``ARRIVED`` until the session ends, with a reason (and a note for ``OTHER``).
The session's place is released under its row lock; its token is not (R4, AC2). The history
row and the audit row commit with it. The audit row carries the reason code, never the note.
"""

from __future__ import annotations

from dataclasses import dataclass
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
from mediease_api.domain.appointments.status import CancelReason
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CancelCommand:
    reason: CancelReason
    note: str | None = None


class CancelAppointment:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, *, clinic_id: UUID, actor: Actor, appointment_id: UUID, cmd: CancelCommand
    ) -> AppointmentView:
        with self._uow as uow:
            tenant = uow.tenant(clinic_id)
            seen = load_appointment(tenant, clinic_id, appointment_id)
            session = lock_sessions(tenant, clinic_id, [seen.session_id]).sessions[seen.session_id]
            # Re-read under the session lock every change to it takes.
            appointment = load_appointment(tenant, clinic_id, appointment_id, for_update=True)
            before = appointment.status
            now = self._clock.now()
            appointment.cancel(session, reason=cmd.reason, note=cmd.note, now=now)

            tenant.appointments.update(appointment)
            tenant.sessions.update(session)
            record_history(tenant, appointment, ids=self._ids, actor=actor, from_status=before)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.APPOINTMENT_CANCELLED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=appointment.id,
                metadata={
                    **place_metadata(appointment, session),
                    "from_status": before.value,
                    "cancel_reason": cmd.reason.value,
                },
            )
            uow.commit()

        logger.info(
            "appointment.cancelled",
            clinic_id=str(clinic_id),
            appointment_id=str(appointment.id),
            cancel_reason=cmd.reason.value,
        )
        return AppointmentView(appointment, session)
