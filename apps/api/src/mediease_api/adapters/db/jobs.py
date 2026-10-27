"""Job queue, worker store and retention over SQLAlchemy (M5-P1, ADR-0005).

``SqlAlchemyJobQueue`` shares the unit of work's session, so enqueueing commits or rolls back with
the change that needs it. ``SqlAlchemyJobStore`` opens its own short transaction per call and
commits it before returning: the claim in particular is committed *before* any handler runs, so no
row lock is ever held across a handler or network call (spec R9a).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.db.models import JobRow
from mediease_api.domain.jobs.job import (
    DEDUPE_STATES,
    ClaimedJob,
    JobState,
    NewJob,
    PayloadValue,
)
from mediease_api.domain.jobs.retry import JobFailure, Outcome, decide
from mediease_api.domain.jobs.schedule import PurgeCounts, RetentionCutoffs
from mediease_api.ports.jobs import ReapResult

logger = structlog.get_logger(__name__)

_DEDUPE_WHERE = text("state IN (" + ", ".join(f"'{s.value}'" for s in DEDUPE_STATES) + ")")
# The most jobs one reaper pass recovers; the next pass takes the rest.
_REAP_BATCH = 100

_CLAIM = text(
    """
    WITH due AS (
        SELECT id FROM jobs
        WHERE state = 'queued' AND run_at <= :now
          AND (cardinality(CAST(:only AS text[])) = 0 OR kind = ANY(CAST(:only AS text[])))
          AND NOT (kind = ANY(CAST(:skip AS text[])))
        ORDER BY run_at, id
        LIMIT :limit
        FOR UPDATE SKIP LOCKED
    )
    UPDATE jobs SET state = 'running', attempts = attempts + 1,
                    locked_by = :worker, locked_at = :now, updated_at = :now
    FROM due
    WHERE jobs.id = due.id
    RETURNING jobs.id, jobs.kind, jobs.clinic_id, jobs.payload, jobs.attempts,
              jobs.max_attempts, jobs.request_id, jobs.dedupe_key
    """
)

# Every outcome applies only while this worker still holds the job: same holder, same attempt.
_HELD = "id = :id AND state = 'running' AND locked_by = :by AND attempts = :attempts"

_SUCCEED = text(
    "UPDATE jobs SET state = 'succeeded', finished_at = :now, updated_at = :now,"
    f" locked_by = NULL, locked_at = NULL WHERE {_HELD}"
)
_RETRY = text(
    "UPDATE jobs SET state = 'queued', run_at = :run_at, last_error_code = :code,"
    f" updated_at = :now, locked_by = NULL, locked_at = NULL WHERE {_HELD}"
)
_KILL = text(
    "UPDATE jobs SET state = 'dead', last_error_code = :code, finished_at = :now,"
    f" updated_at = :now, locked_by = NULL, locked_at = NULL WHERE {_HELD}"
)
_CANCEL = text(
    "UPDATE jobs SET state = 'cancelled', last_error_code = :code, finished_at = :now,"
    f" updated_at = :now, locked_by = NULL, locked_at = NULL WHERE {_HELD}"
)
_RELEASE = text(
    "UPDATE jobs SET state = 'queued', attempts = attempts - 1, updated_at = :now,"
    f" locked_by = NULL, locked_at = NULL WHERE {_HELD}"
)
_HEARTBEAT = text(f"UPDATE jobs SET locked_at = :now, updated_at = :now WHERE {_HELD}")


class SqlAlchemyJobQueue:
    """``JobQueue`` on the unit of work's session (the outbox)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(self, job: NewJob) -> bool:
        statement = (
            insert(JobRow)
            .values(
                id=job.id,
                clinic_id=job.clinic_id,
                kind=job.kind,
                payload=dict(job.payload),
                state=JobState.QUEUED.value,
                run_at=job.run_at,
                attempts=0,
                max_attempts=job.max_attempts,
                request_id=job.request_id,
                dedupe_key=job.dedupe_key,
                created_at=job.created_at,
                updated_at=job.created_at,
            )
            # Only a live job (R9c) makes this a no-op. RETURNING says whether a row was added;
            # rowcount is not reliable for an ORM insert.
            .on_conflict_do_nothing(index_elements=["dedupe_key"], index_where=_DEDUPE_WHERE)
            .returning(JobRow.id)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None


class SqlAlchemyJobStore:
    """``JobStore`` for the worker: each call is one short, committed transaction.

    M7b (prescription-uploads R4): a store claims only ``only`` kinds (when given) and never
    ``skip`` kinds, so the upload worker and the default worker split the queue between them
    (``WORKER_QUEUE``) and a slow scan never holds up a reminder.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        only: frozenset[str] = frozenset(),
        skip: frozenset[str] = frozenset(),
    ) -> None:
        self._session_factory = session_factory
        self._only = sorted(only)
        self._skip = sorted(skip)

    def claim(self, worker: str, now: datetime, limit: int) -> Sequence[ClaimedJob]:
        with self._session_factory() as session:
            rows = session.execute(
                _CLAIM,
                {
                    "now": now,
                    "limit": limit,
                    "worker": worker,
                    "only": self._only,
                    "skip": self._skip,
                },
            ).all()
            session.commit()  # before any handler runs (R9a)
        return [
            ClaimedJob(
                id=row.id,
                kind=row.kind,
                clinic_id=row.clinic_id,
                payload=_payload(row.payload),
                attempts=row.attempts,
                max_attempts=row.max_attempts,
                request_id=row.request_id,
                locked_by=worker,
                dedupe_key=row.dedupe_key,
            )
            for row in rows
        ]

    def heartbeat(self, job: ClaimedJob, now: datetime) -> bool:
        return self._apply(_HEARTBEAT, job, {"now": now})

    def succeed(self, job: ClaimedJob, now: datetime) -> bool:
        return self._apply(_SUCCEED, job, {"now": now})

    def retry(self, job: ClaimedJob, now: datetime, run_at: datetime, code: str) -> bool:
        return self._apply(_RETRY, job, {"now": now, "run_at": run_at, "code": code})

    def kill(self, job: ClaimedJob, now: datetime, code: str) -> bool:
        return self._apply(_KILL, job, {"now": now, "code": code})

    def cancel(self, job: ClaimedJob, now: datetime, code: str) -> bool:
        return self._apply(_CANCEL, job, {"now": now, "code": code})

    def release(self, job: ClaimedJob, now: datetime) -> bool:
        return self._apply(_RELEASE, job, {"now": now})

    def reap(
        self,
        now: datetime,
        stale_after: timedelta,
        failure: JobFailure,
        rand: Callable[[], float],
    ) -> ReapResult:
        requeued = dead = 0
        with self._session_factory() as session:
            stale = session.execute(
                text(
                    "SELECT id, attempts, max_attempts, kind FROM jobs"
                    " WHERE state = 'running' AND locked_at < :cutoff"
                    " ORDER BY locked_at LIMIT :batch FOR UPDATE SKIP LOCKED"
                ),
                {"cutoff": now - stale_after, "batch": _REAP_BATCH},
            ).all()
            for row in stale:
                decision = decide(
                    attempts=row.attempts,
                    max_attempts=row.max_attempts,
                    failure=failure,
                    now=now,
                    rand=rand(),
                )
                if decision.outcome is Outcome.RETRY:
                    session.execute(
                        text(
                            "UPDATE jobs SET state = 'queued', run_at = :run_at,"
                            " last_error_code = :code, updated_at = :now,"
                            " locked_by = NULL, locked_at = NULL WHERE id = :id"
                        ),
                        {
                            "id": row.id,
                            "run_at": decision.run_at,
                            "code": decision.code,
                            "now": now,
                        },
                    )
                    requeued += 1
                else:
                    session.execute(
                        text(
                            "UPDATE jobs SET state = 'dead', last_error_code = :code,"
                            " finished_at = :now, updated_at = :now,"
                            " locked_by = NULL, locked_at = NULL WHERE id = :id"
                        ),
                        {"id": row.id, "code": decision.code, "now": now},
                    )
                    dead += 1
                logger.warning(
                    "job.lock_expired",
                    job_id=str(row.id),
                    job_kind=row.kind,
                    attempts=row.attempts,
                    outcome=decision.outcome.value,
                )
            session.commit()
        return ReapResult(requeued=requeued, dead=dead)

    def _apply(self, statement: Any, job: ClaimedJob, params: dict[str, Any]) -> bool:
        values = {"id": job.id, "by": job.locked_by, "attempts": job.attempts, **params}
        with self._session_factory() as session:
            result = session.execute(statement, values)
            session.commit()
        return result.rowcount == 1  # type: ignore[attr-defined,no-any-return]


class SqlAlchemyRetentionRepository:
    """Deletes expired rows by date alone, across clinics (a reviewed exception, like audit)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def purge(self, cutoffs: RetentionCutoffs) -> PurgeCounts:
        # One statement, so a token and the successor it points to can go together; a token whose
        # successor is still kept stays too (replaced_by_id is a foreign key).
        tokens = self._session.execute(
            text(
                "DELETE FROM refresh_tokens t WHERE t.expires_at < :cutoff AND NOT EXISTS ("
                "SELECT 1 FROM refresh_tokens r"
                " WHERE r.replaced_by_id = t.id AND r.expires_at >= :cutoff)"
            ),
            {"cutoff": cutoffs.refresh_tokens},
        )
        # M6a-P3: portal sessions follow the same rule and count with the staff ones.
        patient_tokens = self._session.execute(
            text(
                "DELETE FROM patient_refresh_tokens t WHERE t.expires_at < :cutoff AND NOT EXISTS ("
                "SELECT 1 FROM patient_refresh_tokens r"
                " WHERE r.replaced_by_id = t.id AND r.expires_at >= :cutoff)"
            ),
            {"cutoff": cutoffs.refresh_tokens},
        )
        links = self._session.execute(
            text("DELETE FROM patient_links WHERE expires_at < :cutoff"),
            {"cutoff": cutoffs.patient_links},
        )
        jobs = self._session.execute(
            text(
                "DELETE FROM jobs WHERE"
                " (state IN ('succeeded', 'cancelled') AND finished_at < :finished)"
                " OR (state = 'dead' AND finished_at < :dead)"
            ),
            {"finished": cutoffs.finished_jobs, "dead": cutoffs.dead_jobs},
        )
        events = 0
        if cutoffs.webhook_events is not None:
            deleted = self._session.execute(
                text("DELETE FROM webhook_events WHERE received_at < :cutoff"),
                {"cutoff": cutoffs.webhook_events},
            )
            events = deleted.rowcount  # type: ignore[attr-defined]
        # M6a-P4: email tokens follow the refresh tokens' 30 days after expiry.
        email_tokens = self._session.execute(
            text("DELETE FROM email_tokens WHERE expires_at < :cutoff"),
            {"cutoff": cutoffs.refresh_tokens},
        )
        notifications = 0
        if cutoffs.notifications is not None:
            # M6a-P7: read or not, 90 days after they were created.
            gone = self._session.execute(
                text("DELETE FROM notifications WHERE created_at < :cutoff"),
                {"cutoff": cutoffs.notifications},
            )
            notifications = gone.rowcount  # type: ignore[attr-defined]
        patient_notices = 0
        if cutoffs.notifications is not None:
            # M6b-P6 (portal R61): the patients' notices follow the staff ones.
            gone_patient = self._session.execute(
                text("DELETE FROM patient_notifications WHERE created_at < :cutoff"),
                {"cutoff": cutoffs.notifications},
            )
            patient_notices = gone_patient.rowcount  # type: ignore[attr-defined]
        doses = 0
        if cutoffs.dose_records is not None:
            # M6b-P3b (R53): a year after the course end, or the dose date when open-ended
            # (keep_until, set when the dose was marked). Selected by that date alone.
            gone_doses = self._session.execute(
                text("DELETE FROM dose_records WHERE keep_until < :cutoff"),
                {"cutoff": cutoffs.dose_records},
            )
            doses = gone_doses.rowcount  # type: ignore[attr-defined]
        return PurgeCounts(
            refresh_tokens=tokens.rowcount + patient_tokens.rowcount,  # type: ignore[attr-defined]
            patient_links=links.rowcount,  # type: ignore[attr-defined]
            jobs=jobs.rowcount,  # type: ignore[attr-defined]
            webhook_events=events,
            email_tokens=email_tokens.rowcount,  # type: ignore[attr-defined]
            notifications=notifications,
            dose_records=doses,
            patient_notifications=patient_notices,
        )


def _payload(value: Any) -> dict[str, PayloadValue]:
    return dict(value) if isinstance(value, dict) else {}


__all__ = ["SqlAlchemyJobQueue", "SqlAlchemyJobStore", "SqlAlchemyRetentionRepository"]
