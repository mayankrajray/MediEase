"""Leave and extra sessions on a date (spec R15, R17, R18; decisions D4, D8).

``AddException``: a whole-day ``LEAVE`` (one per doctor and date) removes that day's generated
sessions that have no bookings and returns the booked ones; an ``EXTRA`` block must not overlap
anything the rules already plan on that day, the day before (an overnight block reaching into it)
or the day after (the extra itself running past midnight).

``RemoveException``: the date is reconciled with the rules without it, so a removed extra loses
its unbooked session and a removed leave lets the day generate again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor
from mediease_api.application.scheduling.generation import neighbours, plan_for, reconcile_doctor
from mediease_api.application.scheduling.schedules import load_clinic, load_doctor
from mediease_api.application.scheduling.views import ExceptionChange
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.scheduling.blocks import BlockShape
from mediease_api.domain.scheduling.errors import LeaveExists, ScheduleOverlap
from mediease_api.domain.scheduling.exceptions import (
    ExceptionKind,
    ScheduleException,
    check_editable_date,
)
from mediease_api.domain.scheduling.sessions import horizon, overlaps, session_bounds
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.repositories import RowLock
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "schedule_exception"


@dataclass(frozen=True, slots=True)
class ExceptionCommand:
    kind: ExceptionKind
    on_date: date
    start_time: time | None = None
    end_time: time | None = None
    slot_minutes: int | None = None
    capacity: int | None = None
    note: str | None = None


class AddException:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, *, clinic_id: UUID, actor: Actor, doctor_id: UUID, cmd: ExceptionCommand
    ) -> ExceptionChange:
        with self._uow as uow:
            clinic = load_clinic(uow, clinic_id)
            tenant = uow.tenant(clinic_id)
            doctor = load_doctor(tenant, clinic_id, doctor_id, lock=RowLock.UPDATE)
            now = self._clock.now()
            today = local_date(now, clinic.timezone)
            on_date = check_editable_date(cmd.on_date, today=today, horizon=horizon(today))

            if cmd.kind is ExceptionKind.LEAVE:
                same_day = tenant.schedule_exceptions.list_for_doctor(
                    doctor.id, first=on_date, last=on_date
                )
                if any(e.kind is ExceptionKind.LEAVE for e in same_day):
                    raise LeaveExists()
                exception = ScheduleException.leave(
                    id=self._ids.new_id(),
                    clinic_id=clinic_id,
                    doctor_id=doctor.id,
                    on_date=on_date,
                    now=now,
                    note=cmd.note,
                )
            else:
                if cmd.start_time is None or cmd.end_time is None:
                    raise InvalidValue("start_time", "an extra session needs a start and an end")
                exception = ScheduleException.extra(
                    id=self._ids.new_id(),
                    clinic_id=clinic_id,
                    doctor_id=doctor.id,
                    on_date=on_date,
                    shape=BlockShape(cmd.start_time, cmd.end_time, cmd.slot_minutes, cmd.capacity),
                    mode=clinic.booking_mode,
                    now=now,
                    note=cmd.note,
                )
                assert exception.shape is not None
                wanted = session_bounds(on_date, exception.shape, clinic.timezone)
                for day in neighbours(on_date):
                    for planned in plan_for(tenant, clinic, doctor.id, day):
                        if overlaps(wanted, (planned.starts_at, planned.ends_at)):
                            raise ScheduleOverlap()

            tenant.schedule_exceptions.add(exception)
            kept = reconcile_doctor(
                tenant, clinic=clinic, doctor=doctor, first=on_date, last=on_date, now=now
            )
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.SCHEDULE_EXCEPTION_ADDED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=exception.id,
                metadata={
                    "doctor_id": str(doctor.id),
                    "kind": exception.kind.value,
                    "on_date": on_date.isoformat(),
                    "kept_sessions": str(len(kept)),
                },
            )
            uow.commit()

        logger.info(
            "schedule.exception_added",
            clinic_id=str(clinic_id),
            doctor_id=str(doctor_id),
            kind=exception.kind.value,
            kept_sessions=len(kept),
        )
        return ExceptionChange(exception=exception, kept_sessions=kept)


class RemoveException:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, *, clinic_id: UUID, actor: Actor, doctor_id: UUID, exception_id: UUID
    ) -> ExceptionChange:
        with self._uow as uow:
            clinic = load_clinic(uow, clinic_id)
            tenant = uow.tenant(clinic_id)
            doctor = load_doctor(tenant, clinic_id, doctor_id, lock=RowLock.UPDATE)
            exception = tenant.schedule_exceptions.get(exception_id)
            if exception is None or exception.doctor_id != doctor.id:
                raise NotFound("schedule exception")
            now = self._clock.now()
            if exception.on_date < local_date(now, clinic.timezone):
                raise InvalidValue("on_date", "is in the past: past exceptions are kept as history")

            tenant.schedule_exceptions.delete(exception.id)
            kept = reconcile_doctor(
                tenant,
                clinic=clinic,
                doctor=doctor,
                first=exception.on_date,
                last=exception.on_date,
                now=now,
            )
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.SCHEDULE_EXCEPTION_REMOVED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=exception.id,
                metadata={
                    "doctor_id": str(doctor.id),
                    "kind": exception.kind.value,
                    "on_date": exception.on_date.isoformat(),
                    "kept_sessions": str(len(kept)),
                },
            )
            uow.commit()

        logger.info(
            "schedule.exception_removed",
            clinic_id=str(clinic_id),
            doctor_id=str(doctor_id),
            kind=exception.kind.value,
            kept_sessions=len(kept),
        )
        return ExceptionChange(exception=exception, kept_sessions=kept)
