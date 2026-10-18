"""The worker loop (M5-P1, spec R9, R9a, R10, R11, R11a, ADR-0005).

One process, one loop. Each iteration: (at most once a minute) enqueue the recurring jobs and
reap jobs whose worker died; claim up to a batch of due jobs, each claim committed before any
handler runs; run them one after another; then rewrite the heartbeat file. A failed iteration
backs off and does *not* rewrite it, so a worker that cannot reach the database turns unhealthy.

Everything with a side effect is injected, so the loop is tested without threads, sleeping or a
clock.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import timedelta

import structlog
from structlog.contextvars import bound_contextvars

from mediease_api.application.jobs.run import RunJob
from mediease_api.application.jobs.schedule import ScheduleRecurring
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.retry import (
    HEARTBEAT_EVERY,
    JOB_LOCK_EXPIRED,
    STALE_AFTER,
    JobFailure,
)
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.jobs import JobStore

logger = structlog.get_logger(__name__)

# Scheduler and reaper run at most this often; polling every few seconds is not needed for them.
MAINTENANCE_EVERY = timedelta(minutes=1)
# After a failed iteration the worker waits this long, doubling to the cap (seconds).
MAX_BACKOFF_SECONDS = 30.0


class LockRenewer:
    """Renews a running job's lock every ``every`` seconds while its handler works (R9)."""

    def __init__(self, store: JobStore, clock: ClockPort, every: float | None = None) -> None:
        self._store = store
        self._clock = clock
        self._every = HEARTBEAT_EVERY.total_seconds() if every is None else every

    @contextmanager
    def hold(self, job: ClaimedJob) -> Iterator[None]:
        done = threading.Event()

        def renew() -> None:
            while not done.wait(self._every):
                try:
                    if not self._store.heartbeat(job, self._clock.now()):
                        logger.warning("job.lost_lock", job_id=str(job.id), job_kind=job.kind)
                        return
                except Exception as error:
                    logger.warning("job.heartbeat_failed", error_type=type(error).__name__)

        thread = threading.Thread(target=renew, name=f"lock-renewer-{job.id}", daemon=True)
        thread.start()
        try:
            yield
        finally:
            done.set()
            thread.join(timeout=5)


class Worker:
    def __init__(
        self,
        *,
        worker_id: str,
        store: JobStore,
        run_job: RunJob,
        schedule: ScheduleRecurring,
        clock: ClockPort,
        rand: Callable[[], float],
        request_id: Callable[[], str],
        beat: Callable[[], None],
        sleep: Callable[[float], None],
        stopping: Callable[[], bool],
        batch_size: int,
        poll_seconds: float,
        renewer: Callable[[ClaimedJob], AbstractContextManager[None]],
    ) -> None:
        self._worker_id = worker_id
        self._store = store
        self._run_job = run_job
        self._schedule = schedule
        self._clock = clock
        self._rand = rand
        self._request_id = request_id
        self._beat = beat
        self._sleep = sleep
        self._stopping = stopping
        self._batch_size = batch_size
        self._poll_seconds = poll_seconds
        self._renewer = renewer
        self._next_maintenance = self._clock.now()
        self._failures = 0

    def run(self) -> None:
        logger.info("worker.started", worker_id=self._worker_id)
        while not self._stopping():
            self.iterate()
        logger.info("worker.stopped", worker_id=self._worker_id)

    def iterate(self) -> int:
        """One pass; returns the jobs run. Never raises: a failure backs off and is logged."""
        try:
            ran = self._poll()
        except Exception as error:
            self._failures += 1
            wait = min(MAX_BACKOFF_SECONDS, self._poll_seconds * 2**self._failures)
            logger.error(
                "worker.poll_failed",
                worker_id=self._worker_id,
                error_type=type(error).__name__,
                consecutive=self._failures,
                retry_in_seconds=wait,
            )
            self._sleep(wait)
            return 0
        self._failures = 0
        self._beat()  # only after the database answered (R11a)
        if ran == 0:
            self._sleep(self._poll_seconds)
        return ran

    def _poll(self) -> int:
        now = self._clock.now()
        if now >= self._next_maintenance:
            self._maintain()
            self._next_maintenance = now + MAINTENANCE_EVERY
        jobs = self._store.claim(self._worker_id, now, self._batch_size)
        for position, job in enumerate(jobs):
            if self._stopping():
                # Shutting down: give back what was claimed but not started (not counted).
                for unstarted in jobs[position:]:
                    self._store.release(unstarted, self._clock.now())
                return position
            self._run(job)
        return len(jobs)

    def _maintain(self) -> None:
        added = self._schedule.execute(self._request_id())
        reaped = self._store.reap(
            self._clock.now(), STALE_AFTER, JobFailure(JOB_LOCK_EXPIRED), self._rand
        )
        if added or reaped.requeued or reaped.dead:
            logger.info(
                "worker.maintained",
                enqueued=added,
                reaped_requeued=reaped.requeued,
                reaped_dead=reaped.dead,
            )

    def _run(self, job: ClaimedJob) -> None:
        fields: dict[str, str] = {
            "job_id": str(job.id),
            "job_kind": job.kind,
            "worker_id": self._worker_id,
        }
        if job.request_id:
            fields["request_id"] = job.request_id
        with bound_contextvars(**fields):
            logger.info("job.claimed", attempts=job.attempts, max_attempts=job.max_attempts)
            with self._renewer(job):
                self._run_job.execute(job)
