"""Run one claimed job and record how it ended (M5-P1, spec R9a, R9b, R9d).

The claim was committed before this runs (R9a), so nothing here holds a lock: the handler works in
its own units of work and the outcome is a separate short write. If this process dies in between,
the attempt is already counted and the reaper recovers the job (R10).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import structlog

from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.retry import (
    JOB_CLINIC_SUSPENDED,
    JOB_HANDLER_ERROR,
    JOB_HANDLER_MISSING,
    JOB_MAX_ATTEMPTS,
    JobFailure,
    Outcome,
    decide,
)
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.jobs import JobStore
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# A handler does its work in its own unit(s) of work and returns nothing; a failure is a
# ``JobFailure`` (any other exception is treated as a retryable ``JOB_HANDLER_ERROR``).
JobHandler = Callable[[ClaimedJob], None]


class RunJob:
    def __init__(
        self,
        *,
        store: JobStore,
        handlers: Mapping[str, JobHandler],
        uow: UnitOfWork,
        clock: ClockPort,
        rand: Callable[[], float],
    ) -> None:
        self._store = store
        self._handlers = handlers
        self._uow = uow
        self._clock = clock
        self._rand = rand

    def execute(self, job: ClaimedJob) -> None:
        if self._clinic_is_suspended(job):
            held = self._store.cancel(job, self._clock.now(), JOB_CLINIC_SUSPENDED)
            self._report(job, "job.cancelled", held, error_code=JOB_CLINIC_SUSPENDED)
            return
        failure = self._attempt(job)
        now = self._clock.now()
        if failure is None:
            self._report(job, "job.succeeded", self._store.succeed(job, now))
            return
        decision = decide(
            attempts=job.attempts,
            max_attempts=job.max_attempts,
            failure=failure,
            now=now,
            rand=self._rand(),
        )
        if decision.outcome is Outcome.RETRY and decision.run_at is not None:
            held = self._store.retry(job, now, decision.run_at, decision.code)
            self._report(
                job,
                "job.retry_scheduled",
                held,
                error_code=decision.code,
                run_at=decision.run_at.isoformat(),
            )
        else:
            held = self._store.kill(job, now, decision.code)
            reason = JOB_MAX_ATTEMPTS if decision.exhausted else "permanent"
            self._report(job, "job.dead", held, error_code=decision.code, reason=reason)

    def _clinic_is_suspended(self, job: ClaimedJob) -> bool:
        if job.clinic_id is None:
            return False
        with self._uow as uow:
            clinic = uow.clinics.get(job.clinic_id)
        return clinic is None or clinic.status is ClinicStatus.SUSPENDED

    def _attempt(self, job: ClaimedJob) -> JobFailure | None:
        handler = self._handlers.get(job.kind)
        if handler is None:
            return JobFailure(JOB_HANDLER_MISSING)
        try:
            handler(job)
        except JobFailure as failure:
            return failure
        except Exception as error:
            # The exception's type only: its message could carry patient data.
            logger.warning("job.handler_error", job_id=str(job.id), error_type=type(error).__name__)
            return JobFailure(JOB_HANDLER_ERROR)
        return None

    def _report(self, job: ClaimedJob, event: str, held: bool, **fields: object) -> None:
        if not held:
            logger.warning("job.lost_lock", job_id=str(job.id), job_kind=job.kind, wanted=event)
            return
        logger.info(
            event,
            job_id=str(job.id),
            job_kind=job.kind,
            attempts=job.attempts,
            clinic_id=str(job.clinic_id) if job.clinic_id else None,
            **fields,
        )
