"""Booking requests and their soft hold (M6b-P4; PRD FR-PUB-02, FR-BKG-01, 02, 07; ADR-0018).

A patient asks a clinic for a time; the clinic decides (P5). Until then the request **holds** the
slot (or one place of a token session) for a short time so two patients are never both told
"requested" for it, while the request itself stays open longer:

- the **hold** lasts ``Clinic.request_hold_minutes`` (default 2 hours) and never past the
  response deadline; it ends by time alone, or at once when staff override it;
- the **response deadline** ``respond_by`` is 4 hours after the request, or 1 hour before the slot
  if that is sooner (FR-BKG-06). P5 expires the request then.

A request is a *live hold* while it is ``PENDING`` and ``hold_expires_at`` is in the future.
Everything that takes a place (a staff booking, a new request, P5's accept) counts live holds under
the session's row lock, so a hold needs no job to lapse.

The reason is clinical text (C3): never logged, never in a notification or an error. The phone is
masked in logs; age and sex are never logged.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.patients.patient import Sex
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import optional_text
from mediease_api.domain.shared.time import require_utc

REASON_MAX = 200
AGE_MAX = 120
# FR-BKG-06: how long a request may stay open, or until this long before the slot.
RESPONSE_WINDOW = timedelta(hours=4)
RESPONSE_LEAD = timedelta(hours=1)
# A slot is offered only if its deadline (RESPONSE_LEAD before it) is still ahead (R6).
MIN_LEAD = timedelta(hours=2)
HORIZON_DAYS = 14
# FR-BKG-07: open requests per account, across clinics.
MAX_OPEN_REQUESTS = 5
HOLD_MINUTES_RANGE = range(30, 481)
DEFAULT_HOLD_MINUTES = 120


class RequestStatus(StrEnum):
    """P4 creates ``PENDING`` only; P5 adds the outcomes."""

    PENDING = "PENDING"


class TooManyRequests(DomainError):
    """FR-BKG-07: five open requests per account."""

    code = "PRT_TOO_MANY_REQUESTS"

    def __init__(self) -> None:
        super().__init__(
            "You have 5 open requests. Wait for a clinic to answer one before asking for another."
        )


class RequestExists(DomainError):
    """One open request per account and session."""

    code = "PRT_REQUEST_EXISTS"

    def __init__(self) -> None:
        super().__init__("You have already asked for this session. The clinic will reply.")


class BookingRateLimited(DomainError):
    """FR-BKG-07, NFR-19: too many requests or reads from this account, phone or address."""

    code = "PRT_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many attempts. Please wait a little and try again.")
        self.retry_after_seconds = retry_after_seconds


def response_deadline(*, now: datetime, starts_at: datetime) -> datetime:
    """FR-BKG-06: 4 hours from now, or 1 hour before the slot if sooner."""
    return min(now + RESPONSE_WINDOW, starts_at - RESPONSE_LEAD)


@dataclass(slots=True)
class BookingRequest:
    """Build with ``create``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    doctor_id: UUID
    session_id: UUID
    slot_start: datetime | None
    account_id: UUID
    contact_phone: PhoneNumber
    age_years: int | None
    sex: Sex | None
    reason: str | None
    status: RequestStatus
    hold_expires_at: datetime
    respond_by: datetime
    hold_overridden_at: datetime | None
    hold_overridden_by: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        doctor_id: UUID,
        session_id: UUID,
        slot_start: datetime | None,
        starts_at: datetime,
        account_id: UUID,
        contact_phone: PhoneNumber,
        age_years: int | None,
        sex: Sex | None,
        reason: str | None,
        not_emergency_ack: bool,
        requires_age_sex: bool,
        hold_minutes: int,
        now: datetime,
    ) -> BookingRequest:
        """``starts_at`` is the slot's start, or the session's in token mode (R11, R12)."""
        now = require_utc(now, "now")
        starts_at = require_utc(starts_at, "starts_at")
        if not not_emergency_ack:
            raise InvalidValue("not_emergency_ack", "must be confirmed")
        if starts_at - now < MIN_LEAD:
            raise InvalidValue("slot_start", "must be at least 2 hours from now")
        if age_years is not None and not 0 <= age_years <= AGE_MAX:
            raise InvalidValue("age_years", f"must be 0-{AGE_MAX}")
        if requires_age_sex:
            if age_years is None:
                raise InvalidValue("age_years", "is required by this clinic")
            if sex is None:
                raise InvalidValue("sex", "is required by this clinic")
        if hold_minutes not in HOLD_MINUTES_RANGE:
            raise InvalidValue("hold_minutes", "must be 30-480")
        deadline = response_deadline(now=now, starts_at=starts_at)
        return cls(
            id=id,
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            session_id=session_id,
            slot_start=slot_start,
            account_id=account_id,
            contact_phone=contact_phone,
            age_years=age_years,
            sex=sex,
            reason=optional_text(reason, "reason", max_length=REASON_MAX),
            status=RequestStatus.PENDING,
            hold_expires_at=min(now + timedelta(minutes=hold_minutes), deadline),
            respond_by=deadline,
            hold_overridden_at=None,
            hold_overridden_by=None,
            created_at=now,
            updated_at=now,
        )

    def is_live_hold(self, now: datetime) -> bool:
        """ADR-0018: pending and not yet lapsed or overridden."""
        return self.status is RequestStatus.PENDING and self.hold_expires_at > now

    def override_hold(self, *, by: UUID, now: datetime) -> None:
        """R18a: staff booked over it. The hold ends now; the request stays pending for P5."""
        now = require_utc(now, "now")
        self.hold_expires_at = now
        self.hold_overridden_at = now
        self.hold_overridden_by = by
        self.updated_at = now


def newest_first(holds: Iterable[BookingRequest]) -> list[BookingRequest]:
    return sorted(holds, key=lambda h: (h.created_at, str(h.id)), reverse=True)
