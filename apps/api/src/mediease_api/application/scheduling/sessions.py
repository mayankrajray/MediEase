"""The sessions of one date (spec R1-R4; decision D1): generated lazily, read by every role.

Reading a date from the clinic's today up to 180 days ahead first inserts the sessions the rules
plan and that do not exist yet (idempotent: ``ON CONFLICT DO NOTHING``), under a shared lock on
each doctor's row, so it never runs alongside a schedule change (R20) but many screens can read at
once. An earlier date shows what was generated then; a later one is refused. Each session comes
with the slots its active appointments hold (M3-P2), so a screen can show which are free.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

import structlog

from mediease_api.application.appointments.views import SessionView
from mediease_api.application.context import RequestContext
from mediease_api.application.scheduling.generation import generate
from mediease_api.application.scheduling.schedules import load_clinic, load_doctor
from mediease_api.domain.scheduling.sessions import horizon
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.repositories import RowLock
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class ListSessions:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, ctx: RequestContext, on_date: date, *, doctor_id: UUID | None = None
    ) -> Sequence[SessionView]:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            now = self._clock.now()
            today = local_date(now, clinic.timezone)
            if on_date > horizon(today):
                raise InvalidValue("date", "must be at most 180 days ahead")

            if doctor_id is not None:
                doctor_ids = [load_doctor(tenant, ctx.clinic_id, doctor_id).id]
            else:
                doctor_ids = [d.id for d in tenant.doctors.list() if d.is_active]

            created = 0
            if on_date >= today:
                # In ID order, like a booking-mode change, so two lockers never wait on each other.
                for one_id in sorted(doctor_ids):
                    doctor = load_doctor(tenant, ctx.clinic_id, one_id, lock=RowLock.SHARE)
                    created += generate(
                        tenant,
                        clinic=clinic,
                        doctor=doctor,
                        on_date=on_date,
                        ids=self._ids,
                        now=now,
                    )
            sessions = tenant.sessions.list_for_date(on_date, doctor_id=doctor_id)
            taken: dict[UUID, set[datetime]] = {}
            for appointment in tenant.appointments.list_active_for_sessions(
                [s.id for s in sessions]
            ):
                if appointment.slot_start is not None:
                    taken.setdefault(appointment.session_id, set()).add(appointment.slot_start)
            uow.commit()

        if created:
            logger.info("session.generated", clinic_id=str(ctx.clinic_id), count=created)
        return [SessionView(s, frozenset(taken.get(s.id, ()))) for s in sessions]
