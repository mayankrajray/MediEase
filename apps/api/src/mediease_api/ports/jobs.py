"""Ports for background jobs (M5-P1, ADR-0005).

Two sides of the same table. ``JobQueue`` is on the unit of work: a use case enqueues a job in
the transaction of the change that needs it (the outbox), so it exists if and only if the change
committed. ``JobStore`` is the worker's side: every call is its own short transaction, so a row
lock is never held while a handler runs (spec R9a).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from mediease_api.domain.jobs.job import ClaimedJob, NewJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.jobs.schedule import PurgeCounts, RetentionCutoffs


class JobQueue(Protocol):
    def enqueue(self, job: NewJob) -> bool:
        """Save ``job`` in the open transaction. False if a live job already has its key (R9c)."""
        ...


@dataclass(frozen=True, slots=True)
class ReapResult:
    requeued: int
    dead: int


class JobStore(Protocol):
    """The worker's view. ``False`` from an outcome call means this worker no longer holds the
    job (its lock expired and the reaper or another worker took it): nothing was changed."""

    def claim(self, worker: str, now: datetime, limit: int) -> Sequence[ClaimedJob]:
        """Move up to ``limit`` due jobs to ``running``, counting the attempt, and commit (R9a)."""
        ...

    def heartbeat(self, job: ClaimedJob, now: datetime) -> bool: ...
    def succeed(self, job: ClaimedJob, now: datetime) -> bool: ...
    def retry(self, job: ClaimedJob, now: datetime, run_at: datetime, code: str) -> bool: ...
    def kill(self, job: ClaimedJob, now: datetime, code: str) -> bool: ...
    def cancel(self, job: ClaimedJob, now: datetime, code: str) -> bool: ...

    def release(self, job: ClaimedJob, now: datetime) -> bool:
        """Hand back a job that was claimed but will not be run (shutdown): not counted."""
        ...

    def reap(
        self,
        now: datetime,
        stale_after: timedelta,
        failure: JobFailure,
        rand: Callable[[], float],
    ) -> ReapResult:
        """Recover jobs whose lock is older than ``stale_after`` (R10): back to the queue after
        the back-off while attempts remain, otherwise dead."""
        ...


class RetentionRepository(Protocol):
    """Deletes rows past their retention (DATA_MODEL "Retention and erasure").

    Reviewed cross-clinic exception, like the audit writer: it deletes by expiry date alone and
    never reads a row's content.
    """

    def purge(self, cutoffs: RetentionCutoffs) -> PurgeCounts: ...
