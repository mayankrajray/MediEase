"""The automatic no-show (appointments spec R10; M5-P4 decision 4A).

Every 5 minutes the system job ``schedule_no_shows`` asks which active clinics have bookings still
``BOOKED`` an hour after their session ended (clinic IDs only) and enqueues one ``mark_no_shows``
job per clinic, keyed by the 5-minute period. That job reads and changes only its own clinic's
appointments: each one is locked, checked again, set to ``NO_SHOW``, and gets a history row with no
user and a ``SYSTEM`` audit event. A late arrival can still move it to ``ARRIVED`` the same day.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from mediease_api.application.appointments.common import ENTITY_TYPE
from mediease_api.domain.appointments.appointment import history_entry
from mediease_api.domain.appointments.queue import mark_no_show_automatically, no_show_cutoff
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.jobs.job import (
    MARK_NO_SHOWS_KIND,
    NO_SHOW_SWEEP_KIND,
    ClaimedJob,
    NewJob,
)
from mediease_api.domain.jobs.schedule import RECURRING, dedupe_key
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# One clinic's job changes at most this many per run; the next run takes the rest.
BATCH = 200


class SweepNoShows:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def __call__(self, job: ClaimedJob) -> None:
        now = self._clock.now()
        period = next(r for r in RECURRING if r.kind == NO_SHOW_SWEEP_KIND)
        suffix = dedupe_key(period, now)  # one job per clinic per 5-minute period
        enqueued = 0
        with self._uow as uow:
            for clinic_id in uow.no_show_sweep.clinics_with_overdue(
                ended_before=no_show_cutoff(now)
            ):
                added = uow.jobs.enqueue(
                    NewJob.create(
                        id=self._ids.new_id(),
                        kind=MARK_NO_SHOWS_KIND,
                        now=now,
                        clinic_id=clinic_id,
                        request_id=job.request_id,
                        dedupe_key=f"{MARK_NO_SHOWS_KIND}:{clinic_id}:{suffix}",
                    )
                )
                enqueued += int(added)
            uow.commit()
        if enqueued:
            logger.info("no_show.sweep", clinics=enqueued)


class MarkNoShows:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def __call__(self, job: ClaimedJob) -> None:
        assert job.clinic_id is not None
        clinic_id: UUID = job.clinic_id
        marked = 0
        with self._uow as uow:
            tenant = uow.tenant(clinic_id)
            now = self._clock.now()
            for appointment_id in tenant.appointments.list_booked_ended_before(
                no_show_cutoff(now), limit=BATCH
            ):
                appointment = tenant.appointments.get(appointment_id, for_update=True)
                if appointment is None:  # pragma: no cover - just listed
                    continue
                session = tenant.sessions.get(appointment.session_id)
                assert session is not None
                if not mark_no_show_automatically(appointment, session, now=now):
                    continue  # moved by staff meanwhile
                tenant.appointments.update(appointment)
                tenant.appointment_history.add(
                    history_entry(
                        appointment,
                        id=self._ids.new_id(),
                        from_status=AppointmentStatus.BOOKED,
                        changed_by=None,
                        request_id=job.request_id,
                    )
                )
                uow.audit.record(
                    AuditEvent.record(
                        id=self._ids.new_id(),
                        action=AuditAction.APPOINTMENT_STATUS_CHANGED,
                        actor_type=ActorType.SYSTEM,
                        now=now,
                        clinic_id=clinic_id,
                        entity_type=ENTITY_TYPE,
                        entity_id=appointment.id,
                        request_id=job.request_id,
                        metadata={
                            "from": AppointmentStatus.BOOKED.value,
                            "to": AppointmentStatus.NO_SHOW.value,
                            "session_id": str(session.id),
                            "doctor_id": str(session.doctor_id),
                            "automatic": "true",
                        },
                    )
                )
                marked += 1
            uow.commit()
        logger.info("no_show.marked", clinic_id=str(clinic_id), appointments=marked)
