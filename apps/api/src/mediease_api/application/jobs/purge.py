"""The retention purge: the first real job (M5-P1, DATA_MODEL "Retention and erasure").

Deletes refresh tokens and patient links 30 days after they expired, finished jobs after 30
days (dead ones after 90, kept longer to investigate) and stored webhook events after 7 (M5-P3).
One ``retention.purged`` audit event is
written as SYSTEM with the counts only, in the same transaction as the deletes.
"""

from __future__ import annotations

import structlog

from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.schedule import PurgeCounts, RetentionCutoffs
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class PurgeExpired:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self) -> PurgeCounts:
        now = self._clock.now()
        with self._uow as uow:
            counts = uow.retention.purge(RetentionCutoffs.at(now))
            uow.audit.record(
                AuditEvent.record(
                    id=self._ids.new_id(),
                    action=AuditAction.RETENTION_PURGED,
                    actor_type=ActorType.SYSTEM,
                    now=now,
                    metadata={
                        "refresh_tokens": str(counts.refresh_tokens),
                        "patient_links": str(counts.patient_links),
                        "jobs": str(counts.jobs),
                        "webhook_events": str(counts.webhook_events),
                    },
                )
            )
            uow.commit()
        logger.info(
            "retention.purged",
            refresh_tokens=counts.refresh_tokens,
            patient_links=counts.patient_links,
            jobs=counts.jobs,
            webhook_events=counts.webhook_events,
        )
        return counts

    def __call__(self, job: ClaimedJob) -> None:
        self.execute()
