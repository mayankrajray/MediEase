"""Booking requests and their soft hold (M6b-P4; PRD FR-PUB-02, FR-BKG-01, 02, 07; ADR-0018).

A patient asks a clinic for a time; the clinic decides (P5). Until then the request **holds** the
slot (or one place of a token session) for a short time so two patients are never both told
"requested" for it, while the request itself stays open longer:

- the **hold** lasts ``Clinic.request_hold_minutes`` (default 2 hours) and never past the
  response deadline; it ends by time alone, or at once when staff override it;
- the **response deadline** ``respond_by`` is 4 hours after the request, or 1 hour before the slot
  if that is sooner (FR-BKG-06). P5 expires the request then.

M6b-P5 (spec R31-R43): staff **accept**, **decline** or **propose** another time; the patient
accepts or declines a proposal; an open request past its deadline is **expired**. Exactly one
answer wins: every answer runs under the request's row lock and calls ``_require_open`` (R31a).
``PROPOSED`` moves the hold to the proposed time and its deadline becomes the hold's end.

A request is a *live hold* while it is open (``PENDING`` or ``PROPOSED``) and ``hold_expires_at``
is in the future.
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
    """R31. ``PENDING`` and ``PROPOSED`` are open; the rest are final."""

    PENDING = "PENDING"
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"


OPEN_STATUSES: frozenset[RequestStatus] = frozenset({RequestStatus.PENDING, RequestStatus.PROPOSED})
NOTE_MAX = 200


class DeclineReason(StrEnum):
    """R39: what the patient is told, in their language. ``PATIENT_DECLINED`` is the patient's own
    *No thanks* to a proposal (R43) and never a staff choice."""

    TIME_UNAVAILABLE = "TIME_UNAVAILABLE"
    DOCTOR_UNAVAILABLE = "DOCTOR_UNAVAILABLE"
    PLEASE_CALL = "PLEASE_CALL"
    NOT_ONLINE = "NOT_ONLINE"
    DUPLICATE = "DUPLICATE"
    OTHER = "OTHER"
    PATIENT_DECLINED = "PATIENT_DECLINED"


STAFF_DECLINE_REASONS: frozenset[DeclineReason] = frozenset(DeclineReason) - {
    DeclineReason.PATIENT_DECLINED
}


class DecidedBy(StrEnum):
    """Who made the request final: staff, the patient (a proposal) or the expiry sweep."""

    STAFF = "STAFF"
    PATIENT = "PATIENT"
    SYSTEM = "SYSTEM"


class AlreadyAnswered(DomainError):
    """R31a: the request is no longer open (answered, or past its deadline)."""

    code = "BKG_ALREADY_ANSWERED"

    def __init__(self) -> None:
        super().__init__("This request has already been answered or has expired.")


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
    # M6b-P5 (R34-R43, R46). ``answered_*``: the staff member's first answer (accept, decline or
    # propose), always before the deadline because an expired request cannot be answered.
    # ``decided_*``: how and when it became final.
    patient_id: UUID | None = None
    appointment_id: UUID | None = None
    answered_at: datetime | None = None
    answered_by: UUID | None = None
    decided_at: datetime | None = None
    decided_by_type: DecidedBy | None = None
    decline_reason: DeclineReason | None = None
    decline_note: str | None = None
    original_session_id: UUID | None = None
    original_slot_start: datetime | None = None

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

    def is_open(self, now: datetime) -> bool:
        """R32: answerable: an open status and the deadline still ahead."""
        return self.status in OPEN_STATUSES and self.respond_by > now

    def effective_status(self, now: datetime) -> RequestStatus:
        """R32: what the request is now, before the sweep has written ``EXPIRED``."""
        if self.status in OPEN_STATUSES and self.respond_by <= now:
            return RequestStatus.EXPIRED
        return self.status

    def is_live_hold(self, now: datetime) -> bool:
        """ADR-0018, R33: open and the hold not yet lapsed or overridden."""
        return self.status in OPEN_STATUSES and self.hold_expires_at > now

    def _require_open(self, now: datetime, *, status: RequestStatus | None = None) -> datetime:
        now = require_utc(now, "now")
        if not self.is_open(now) or (status is not None and self.status is not status):
            raise AlreadyAnswered()
        return now

    def _end_hold(self, now: datetime) -> None:
        self.hold_expires_at = min(self.hold_expires_at, now)

    def _finish(self, status: RequestStatus, by: DecidedBy, now: datetime) -> None:
        self.status = status
        self.decided_by_type = by
        self.decided_at = now
        self.updated_at = now
        self._end_hold(now)

    def _answer(self, by: UUID, now: datetime) -> None:
        if self.answered_at is None:
            self.answered_at = now
            self.answered_by = by

    def accept(
        self,
        *,
        patient_id: UUID,
        appointment_id: UUID,
        by: DecidedBy,
        user_id: UUID | None,
        now: datetime,
    ) -> None:
        """R34 (staff, a ``PENDING`` request) or R42 (the patient takes a ``PROPOSED`` one, for the
        record staff chose with the proposal). A proposal waits for the patient, not the desk."""
        now = self._require_open(
            now,
            status=RequestStatus.PROPOSED if by is DecidedBy.PATIENT else RequestStatus.PENDING,
        )
        if self.status is RequestStatus.PROPOSED and patient_id != self.patient_id:
            raise InvalidValue("patient_id", "must be the record chosen with the proposal")
        if by is DecidedBy.STAFF:
            assert user_id is not None
            self._answer(user_id, now)
        self.patient_id = patient_id
        self.appointment_id = appointment_id
        self._finish(RequestStatus.ACCEPTED, by, now)

    def decline(
        self,
        *,
        reason: DeclineReason,
        note: str | None,
        by: DecidedBy,
        user_id: UUID | None,
        now: datetime,
    ) -> None:
        """R39 (staff, a pending or proposed request) or R43 (*No thanks*, a proposal only)."""
        if by is DecidedBy.PATIENT:
            now = self._require_open(now, status=RequestStatus.PROPOSED)
            reason, note = DeclineReason.PATIENT_DECLINED, None
        else:
            now = self._require_open(now)
            if reason not in STAFF_DECLINE_REASONS:
                raise InvalidValue("reason", "is not a staff reason")
            assert user_id is not None
            self._answer(user_id, now)
        self.decline_reason = reason
        self.decline_note = optional_text(note, "note", max_length=NOTE_MAX)
        self._finish(RequestStatus.DECLINED, by, now)

    def propose(
        self,
        *,
        session_id: UUID,
        slot_start: datetime | None,
        starts_at: datetime,
        patient_id: UUID,
        hold_minutes: int,
        user_id: UUID,
        now: datetime,
    ) -> None:
        """R40, R41: once, for a pending request. The hold moves to the new time, never past an
        hour before it, and the request's deadline becomes the hold's end (R32)."""
        now = self._require_open(now, status=RequestStatus.PENDING)
        starts_at = require_utc(starts_at, "starts_at")
        if starts_at - now < MIN_LEAD:
            raise InvalidValue("session_id", "must start at least 2 hours from now")
        if session_id == self.session_id and slot_start == self.slot_start:
            raise InvalidValue("session_id", "is the time already asked for")
        if hold_minutes not in HOLD_MINUTES_RANGE:
            raise InvalidValue("hold_minutes", "must be 30-480")
        self.original_session_id = self.session_id
        self.original_slot_start = self.slot_start
        self.session_id = session_id
        self.slot_start = slot_start
        self.patient_id = patient_id
        self.hold_expires_at = min(now + timedelta(minutes=hold_minutes), starts_at - RESPONSE_LEAD)
        self.respond_by = self.hold_expires_at
        self.hold_overridden_at = None
        self.hold_overridden_by = None
        self.status = RequestStatus.PROPOSED
        self._answer(user_id, now)
        self.updated_at = now

    def expire(self, now: datetime) -> bool:
        """R32: the sweep writes what ``effective_status`` already says. False if not due."""
        now = require_utc(now, "now")
        if (
            self.effective_status(now) is not RequestStatus.EXPIRED
            or self.status not in OPEN_STATUSES
        ):
            return False
        self._finish(RequestStatus.EXPIRED, DecidedBy.SYSTEM, now)
        return True

    def override_hold(self, *, by: UUID, now: datetime) -> None:
        """R18a: staff booked over it. The hold ends now; the request stays pending for P5."""
        now = require_utc(now, "now")
        self.hold_expires_at = now
        self.hold_overridden_at = now
        self.hold_overridden_by = by
        self.updated_at = now


def newest_first(holds: Iterable[BookingRequest]) -> list[BookingRequest]:
    return sorted(holds, key=lambda h: (h.created_at, str(h.id)), reverse=True)
