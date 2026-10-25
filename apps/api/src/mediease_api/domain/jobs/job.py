"""Background jobs (M5-P1, ADR-0005, spec reminders-and-messaging R9-R11, R9a-R9e).

A job is a unit of work done later, by the worker, with the change that caused it saved in the
same transaction (the outbox). Payloads carry IDs and enums only: never a name, a phone number
or clinical text (R11, NFR-07).

Lifecycle: ``queued -> running -> succeeded``; ``running -> queued`` to retry; ``dead`` when the
attempts are used up or the failure is permanent; ``cancelled`` when the work no longer applies.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

# The retention purge: runs for the whole platform, so it belongs to no clinic.
PURGE_KIND = "purge_expired_auth_and_links"
# M5-P3: a provider webhook is not addressed to a clinic until its statuses are matched, and the
# hourly reconciliation looks at every clinic's messages.
WEBHOOK_KIND = "process_webhook_event"
RECONCILE_KIND = "reconcile_messages"
# M5-P4 (appointments R10): every 5 minutes, find the clinics with bookings still BOOKED an hour
# after their session ended (IDs only) and enqueue one MARK_NO_SHOWS_KIND job per clinic, which
# works only on that clinic's rows.
NO_SHOW_SWEEP_KIND = "schedule_no_shows"
MARK_NO_SHOWS_KIND = "mark_no_shows"
# M6a-P4 (ADR-0016): verification and password-reset emails. They belong to an account, not a
# clinic, so they are system kinds.
AUTH_EMAIL_KIND = "send_auth_email"
# M6a-P5: an owner's emailed staff invitation. It belongs to a clinic, so it is a clinic kind (no
# migration: only system kinds are listed in ``ck_jobs_system_kind``).
STAFF_INVITE_KIND = "send_staff_invite"
# M6b-P5 (booking-requests R32): every 5 minutes, find the clinics with open requests past their
# deadline (IDs only) and enqueue one EXPIRE_REQUESTS_KIND job per clinic.
REQUEST_EXPIRY_SWEEP_KIND = "schedule_request_expiry"
EXPIRE_REQUESTS_KIND = "expire_booking_requests"
# M6b-P6 (portal R65, R66): every 5 minutes, find the clinics with medicine reminders turned on
# (IDs only) and enqueue one NOTIFY_MEDICINE_DUE_KIND job per clinic; and the email of a booking
# answer (R63), one per notification, a clinic kind.
MEDICINE_DUE_SWEEP_KIND = "schedule_medicine_due"
NOTIFY_MEDICINE_DUE_KIND = "notify_medicine_due"
PATIENT_EMAIL_KIND = "send_patient_email"
# M6c-P1 (clinic-onboarding R9, R12, R14): an application's emails (no clinic yet), and the daily
# deletion of applications never confirmed, with their certificates.
APPLICATION_EMAIL_KIND = "send_application_email"
APPLICATION_PURGE_KIND = "purge_applications"
# R9d: the only kinds allowed to have no clinic. The database CHECK ``ck_jobs_system_kind`` lists
# the same kinds; a test keeps the two in step, and adding a kind is a migration.
SYSTEM_KINDS: frozenset[str] = frozenset(
    {
        PURGE_KIND,
        WEBHOOK_KIND,
        RECONCILE_KIND,
        NO_SHOW_SWEEP_KIND,
        AUTH_EMAIL_KIND,
        REQUEST_EXPIRY_SWEEP_KIND,
        MEDICINE_DUE_SWEEP_KIND,
        APPLICATION_EMAIL_KIND,
        APPLICATION_PURGE_KIND,
    }
)

DEFAULT_MAX_ATTEMPTS = 5
MAX_ATTEMPTS_LIMIT = 20
_KIND = re.compile(r"[a-z][a-z0-9_]{2,63}")
MAX_DEDUPE_KEY_LENGTH = 200
MAX_PAYLOAD_KEYS = 20
MAX_PAYLOAD_VALUE_LENGTH = 200

PayloadValue = str | int | bool | None


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEAD = "dead"
    CANCELLED = "cancelled"


# Jobs in these states hold their ``dedupe_key`` (R9c); a cancelled or dead job does not.
DEDUPE_STATES: tuple[JobState, ...] = (JobState.QUEUED, JobState.RUNNING, JobState.SUCCEEDED)


def check_kind(kind: str) -> str:
    if not _KIND.fullmatch(kind):
        raise InvalidValue("kind", "must be 3-64 lowercase letters, digits or underscores")
    return kind


def _clean_payload(payload: Mapping[str, PayloadValue]) -> Mapping[str, PayloadValue]:
    """IDs, counts and flags: short scalars, a handful of keys, read-only."""
    if len(payload) > MAX_PAYLOAD_KEYS:
        raise InvalidValue("payload", f"must have at most {MAX_PAYLOAD_KEYS} keys")
    for key, value in payload.items():
        if not key:
            raise InvalidValue("payload", "keys must not be empty")
        if value is not None and not isinstance(value, str | int | bool):
            raise InvalidValue("payload", f"value of '{key}' must be a string, number or flag")
        if isinstance(value, str) and len(value) > MAX_PAYLOAD_VALUE_LENGTH:
            raise InvalidValue(
                "payload", f"value of '{key}' must be at most {MAX_PAYLOAD_VALUE_LENGTH} chars"
            )
    return MappingProxyType(dict(payload))


@dataclass(frozen=True, slots=True)
class NewJob:
    """A job to enqueue. Build with ``NewJob.create``."""

    id: UUID
    kind: str
    clinic_id: UUID | None
    payload: Mapping[str, PayloadValue]
    run_at: datetime
    max_attempts: int
    request_id: str | None
    dedupe_key: str | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        kind: str,
        now: datetime,
        clinic_id: UUID | None = None,
        payload: Mapping[str, PayloadValue] | None = None,
        run_at: datetime | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        request_id: str | None = None,
        dedupe_key: str | None = None,
    ) -> NewJob:
        check_kind(kind)
        if (clinic_id is None) != (kind in SYSTEM_KINDS):
            raise InvalidValue(
                "clinic_id",
                "is required unless the job is a system job, and a system job has none",
            )
        if not 1 <= max_attempts <= MAX_ATTEMPTS_LIMIT:
            raise InvalidValue("max_attempts", f"must be 1-{MAX_ATTEMPTS_LIMIT}")
        if dedupe_key is not None and not 1 <= len(dedupe_key) <= MAX_DEDUPE_KEY_LENGTH:
            raise InvalidValue("dedupe_key", f"must be 1-{MAX_DEDUPE_KEY_LENGTH} characters")
        if request_id is not None and not 1 <= len(request_id) <= 64:
            raise InvalidValue("request_id", "must be 1-64 characters")
        return cls(
            id=id,
            kind=kind,
            clinic_id=clinic_id,
            payload=_clean_payload(payload or {}),
            run_at=require_utc(run_at or now, "run_at"),
            max_attempts=max_attempts,
            request_id=request_id,
            dedupe_key=dedupe_key,
            created_at=require_utc(now, "now"),
        )


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    """A job this worker holds: ``attempts`` already counts the run about to start (R9a)."""

    id: UUID
    kind: str
    clinic_id: UUID | None
    payload: Mapping[str, PayloadValue]
    attempts: int
    max_attempts: int
    request_id: str | None
    locked_by: str
    dedupe_key: str | None = field(default=None)
