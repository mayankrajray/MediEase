"""Retries, back-off and the dead state (spec R9b, R10).

Pure decisions: given how many attempts were made and how the last one failed, say what happens
next. The caller supplies the time and a random number in ``[0, 1)``, so nothing here reads a
clock or a random source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

# Error codes a job can end with (docs/ERRORS.md "Jobs"). Handlers may add their own (``MSG_*``).
JOB_HANDLER_MISSING = "JOB_HANDLER_MISSING"
JOB_HANDLER_ERROR = "JOB_HANDLER_ERROR"
JOB_LOCK_EXPIRED = "JOB_LOCK_EXPIRED"
JOB_MAX_ATTEMPTS = "JOB_MAX_ATTEMPTS"
JOB_CLINIC_SUSPENDED = "JOB_CLINIC_SUSPENDED"

# Wait after attempt 1, 2, 3 and every later one (R9b), plus up to 10% jitter.
BACKOFF: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=60),
)
JITTER_FRACTION = 0.10

# A running job whose lock is older than this has lost its worker (R10).
STALE_AFTER = timedelta(minutes=5)
# A running handler renews its lock this often (R9).
HEARTBEAT_EVERY = timedelta(seconds=60)


class JobFailure(Exception):
    """How an attempt failed. ``retryable`` failures go back to the queue while attempts remain."""

    def __init__(self, code: str, *, retryable: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable

    def __str__(self) -> str:
        return self.code


class Outcome(StrEnum):
    RETRY = "retry"
    DEAD = "dead"


@dataclass(frozen=True, slots=True)
class Decision:
    outcome: Outcome
    code: str
    run_at: datetime | None = None
    # True when a retryable failure ran out of attempts (logged as JOB_MAX_ATTEMPTS).
    exhausted: bool = False


def delay_after(attempts: int, rand: float) -> timedelta:
    """Back-off after ``attempts`` made so far; ``rand`` in ``[0, 1)`` picks the jitter."""
    base = BACKOFF[min(max(attempts, 1), len(BACKOFF)) - 1]
    return base + base * (JITTER_FRACTION * min(max(rand, 0.0), 1.0))


def decide(
    *, attempts: int, max_attempts: int, failure: JobFailure, now: datetime, rand: float
) -> Decision:
    """What happens after an attempt failed. ``attempts`` already includes that attempt (R9a)."""
    if not failure.retryable:
        return Decision(Outcome.DEAD, failure.code)
    if attempts >= max_attempts:
        return Decision(Outcome.DEAD, failure.code, exhausted=True)
    return Decision(Outcome.RETRY, failure.code, run_at=now + delay_after(attempts, rand))
