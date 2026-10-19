"""Recurring jobs (spec R9e) and retention (DATA_MODEL "Retention and erasure").

A recurring job is enqueued once per period. Its ``dedupe_key`` names the period, so any number of
workers ticking at once still produce one job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mediease_api.domain.jobs.job import NO_SHOW_SWEEP_KIND, PURGE_KIND, RECONCILE_KIND
from mediease_api.domain.shared.time import require_utc

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Recurring:
    kind: str
    period: timedelta


# The platform's recurring jobs. Clinic jobs are never recurring from here; they are enqueued by
# the change that needs them.
RECURRING: tuple[Recurring, ...] = (
    Recurring(PURGE_KIND, timedelta(days=1)),
    # M5-P3: re-run stored webhook events that did not process, and count unconfirmed messages.
    Recurring(RECONCILE_KIND, timedelta(hours=1)),
    # M5-P4: bookings an hour past their session become NO_SHOW (appointments R10).
    Recurring(NO_SHOW_SWEEP_KIND, timedelta(minutes=5)),
)


def period_start(now: datetime, period: timedelta) -> datetime:
    """The start of the period (UTC, counted from the epoch) that contains ``now``."""
    now = require_utc(now, "now")
    elapsed = now - _EPOCH
    return _EPOCH + (elapsed // period) * period


def dedupe_key(recurring: Recurring, now: datetime) -> str:
    return f"{recurring.kind}:{period_start(now, recurring.period).strftime('%Y%m%dT%H%M%SZ')}"


# How long after expiry (or after a job finished) rows are kept.
TOKEN_RETENTION = timedelta(days=30)
LINK_RETENTION = timedelta(days=30)
JOB_RETENTION = timedelta(days=30)
DEAD_JOB_RETENTION = timedelta(days=90)
# M5-P3: stored webhook bodies (statuses only, no text or phone numbers) are kept a week.
WEBHOOK_EVENT_RETENTION = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class RetentionCutoffs:
    """Rows expired or finished before these instants are deleted."""

    refresh_tokens: datetime
    patient_links: datetime
    finished_jobs: datetime
    dead_jobs: datetime
    webhook_events: datetime | None = None

    @classmethod
    def at(cls, now: datetime) -> RetentionCutoffs:
        now = require_utc(now, "now")
        return cls(
            refresh_tokens=now - TOKEN_RETENTION,
            patient_links=now - LINK_RETENTION,
            finished_jobs=now - JOB_RETENTION,
            dead_jobs=now - DEAD_JOB_RETENTION,
            webhook_events=now - WEBHOOK_EVENT_RETENTION,
        )


@dataclass(frozen=True, slots=True)
class PurgeCounts:
    refresh_tokens: int
    patient_links: int
    jobs: int
    webhook_events: int = 0
