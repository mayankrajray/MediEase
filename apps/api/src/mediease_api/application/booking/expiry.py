"""Expiring unanswered booking requests (M6b-P5; FR-BKG-06; spec R32).

Correctness never waits for this: every endpoint treats an open request past its deadline as
expired (``BookingRequest.is_open``). The sweep only **writes** ``EXPIRED`` with a SYSTEM audit row,
so counts and P6's patient notice have a row to act on.

Every 5 minutes the system job ``schedule_request_expiry`` asks which active clinics have open
requests past their deadline (clinic IDs only) and enqueues one ``expire_booking_requests`` job
per clinic, keyed by the period. That job locks each request, checks it again and expires it.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from mediease_api.application.booking.answers import ENTITY_TYPE
from mediease_api.application.notifications.service import publish
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.jobs.job import (
    EXPIRE_REQUESTS_KIND,
    REQUEST_EXPIRY_SWEEP_KIND,
    ClaimedJob,
    NewJob,
)
from mediease_api.domain.jobs.schedule import RECURRING, dedupe_key
from mediease_api.domain.notifications.events import BookingRequestExpired
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

BATCH = 200


class SweepRequestExpiry:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def __call__(self, job: ClaimedJob) -> None:
        now = self._clock.now()
        period = next(r for r in RECURRING if r.kind == REQUEST_EXPIRY_SWEEP_KIND)
        suffix = dedupe_key(period, now)
        enqueued = 0
        with self._uow as uow:
            for clinic_id in uow.booking_request_lookup.clinics_with_overdue(now):
                added = uow.jobs.enqueue(
                    NewJob.create(
                        id=self._ids.new_id(),
                        kind=EXPIRE_REQUESTS_KIND,
                        now=now,
                        clinic_id=clinic_id,
                        request_id=job.request_id,
                        dedupe_key=f"{EXPIRE_REQUESTS_KIND}:{clinic_id}:{suffix}",
                    )
                )
                enqueued += int(added)
            uow.commit()
        if enqueued:
            logger.info("booking_request.expiry_sweep", clinics=enqueued)


class ExpireBookingRequests:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def __call__(self, job: ClaimedJob) -> None:
        assert job.clinic_id is not None
        clinic_id: UUID = job.clinic_id
        expired = 0
        with self._uow as uow:
            tenant = uow.tenant(clinic_id)
            now = self._clock.now()
            for request_id in tenant.booking_requests.list_overdue_ids(now, limit=BATCH):
                request = tenant.booking_requests.get(request_id, for_update=True)
                if request is None or not request.expire(now):
                    continue  # answered meanwhile
                tenant.booking_requests.update(request)
                uow.audit.record(
                    AuditEvent.record(
                        id=self._ids.new_id(),
                        action=AuditAction.BOOKING_REQUEST_EXPIRED,
                        actor_type=ActorType.SYSTEM,
                        now=now,
                        clinic_id=clinic_id,
                        entity_type=ENTITY_TYPE,
                        entity_id=request.id,
                        request_id=job.request_id,
                        metadata={"account_id": str(request.account_id)},
                    )
                )
                # M6b-P6 (portal R57): the requester is told it expired.
                publish(
                    uow,
                    BookingRequestExpired(request.id),
                    clinic_id=clinic_id,
                    ids=self._ids,
                    now=now,
                    request_id=job.request_id,
                )
                expired += 1
            uow.commit()
        logger.info("booking_request.expired", clinic_id=str(clinic_id), requests=expired)
