"""Weekly schedules: read one, replace one (spec R14-R16, R20; decisions D2, D4, D5, D7).

``ReplaceSchedule`` is used by the owner (``SCHEDULES_MANAGE``) and by ops during onboarding; only
the actor differs, so the clinic's ID comes from the caller's authority, never from a body.

A replacement takes effect from the clinic's today. Blocks that were already in force are closed
at yesterday, so past dates keep the rules they were generated from; blocks that had not started
yet are deleted. The doctor's future sessions are then reconciled with the new rules: unbooked
ones that no longer match are deleted (and regenerated on the next read), booked ones are kept and
returned for the owner to reschedule by hand. Nothing is cancelled automatically.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time, timedelta
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.scheduling.generation import reconcile_doctor
from mediease_api.application.scheduling.views import ScheduleChange, ScheduleView
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock, check_no_overlap
from mediease_api.domain.scheduling.sessions import horizon
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.repositories import RowLock
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "doctor"
MAX_BLOCKS = 50


@dataclass(frozen=True, slots=True)
class BlockCommand:
    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int | None = None
    capacity: int | None = None


def load_doctor(
    tenant: TenantRepositories, clinic_id: UUID, doctor_id: UUID, *, lock: RowLock | None = None
) -> Doctor:
    doctor = tenant.doctors.get(doctor_id, lock=lock)
    if doctor is None:
        logger.info(
            "tenancy.not_found", entity="doctor", entity_id=str(doctor_id), clinic_id=str(clinic_id)
        )
        raise NotFound("doctor")
    return doctor


def load_clinic(uow: UnitOfWork, clinic_id: UUID) -> Clinic:
    clinic = uow.clinics.get(clinic_id)
    if clinic is None:
        raise NotFound("clinic")
    return clinic


def schedule_view(
    tenant: TenantRepositories, clinic: Clinic, doctor: Doctor, today: date
) -> ScheduleView:
    return ScheduleView(
        doctor_id=doctor.id,
        booking_mode=clinic.booking_mode,
        blocks=tuple(tenant.schedules.list_for_doctor(doctor.id, valid_since=today)),
        exceptions=tuple(
            tenant.schedule_exceptions.list_for_doctor(doctor.id, first=today, last=horizon(today))
        ),
    )


class GetSchedule:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext, doctor_id: UUID) -> ScheduleView:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            doctor = load_doctor(tenant, ctx.clinic_id, doctor_id)
            return schedule_view(
                tenant, clinic, doctor, local_date(self._clock.now(), clinic.timezone)
            )


class ReplaceSchedule:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, *, clinic_id: UUID, actor: Actor, doctor_id: UUID, blocks: Sequence[BlockCommand]
    ) -> ScheduleChange:
        with self._uow as uow:
            clinic = load_clinic(uow, clinic_id)
            tenant = uow.tenant(clinic_id)
            # R20: one change at a time per doctor, and no generation while it runs.
            doctor = load_doctor(tenant, clinic_id, doctor_id, lock=RowLock.UPDATE)
            now = self._clock.now()
            today = local_date(now, clinic.timezone)

            new_blocks = [
                WeeklyBlock.create(
                    id=self._ids.new_id(),
                    clinic_id=clinic_id,
                    doctor_id=doctor.id,
                    weekday=cmd.weekday,
                    shape=BlockShape(cmd.start_time, cmd.end_time, cmd.slot_minutes, cmd.capacity),
                    mode=clinic.booking_mode,
                    valid_from=today,
                    now=now,
                    index=index,
                )
                for index, cmd in enumerate(blocks)
            ]
            check_no_overlap([b.interval for b in new_blocks])

            for current in tenant.schedules.list_for_doctor(doctor.id, valid_since=today):
                if current.valid_from >= today:
                    tenant.schedules.delete(current.id)
                else:
                    current.close(last_day=today - timedelta(days=1), now=now)
                    tenant.schedules.update(current)
            for block in new_blocks:
                tenant.schedules.add(block)

            kept = reconcile_doctor(tenant, clinic=clinic, doctor=doctor, first=today)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.SCHEDULE_CHANGED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=doctor.id,
                metadata={"blocks": str(len(new_blocks)), "kept_sessions": str(len(kept))},
            )
            view = schedule_view(tenant, clinic, doctor, today)
            uow.commit()

        logger.info(
            "schedule.changed",
            clinic_id=str(clinic_id),
            doctor_id=str(doctor_id),
            blocks=len(new_blocks),
            kept_sessions=len(kept),
        )
        return ScheduleChange(schedule=view, kept_sessions=kept)
