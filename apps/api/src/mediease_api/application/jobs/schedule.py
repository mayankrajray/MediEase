"""Enqueue the recurring jobs once per period (spec R9e)."""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from mediease_api.domain.jobs.job import NewJob
from mediease_api.domain.jobs.schedule import RECURRING, Recurring, dedupe_key
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class ScheduleRecurring:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        recurring: Sequence[Recurring] = RECURRING,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._recurring = recurring

    def execute(self, request_id: str) -> int:
        """Enqueue this period's job for each recurring kind; returns how many were new."""
        added = 0
        for item in self._recurring:
            now = self._clock.now()
            job = NewJob.create(
                id=self._ids.new_id(),
                kind=item.kind,
                now=now,
                request_id=request_id,
                dedupe_key=dedupe_key(item, now),
            )
            with self._uow as uow:
                if uow.jobs.enqueue(job):
                    uow.commit()
                    added += 1
                    logger.info("job.enqueued", job_id=str(job.id), job_kind=job.kind)
        return added
