"""A patient's link to their prescription (spec prescriptions R9-R11; M4-P5 decisions 1A, 6A).

One link per prescription chain, created when version 1 is issued and reused by revisions, so
the page always shows the latest issued version. ``prescription_id`` is version 1's ID. The row
is the authority: the token only proves which row is meant (``token.py``).

Opening needs the last 4 digits of the patient's phone (R10). Five wrong answers lock the link
until clinic staff reset it; a right answer clears the count. The domain never reads a clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.links.errors import (
    LinkExpired,
    LinkInvalid,
    LinkLocked,
    LinkNotLocked,
    LinkRevoked,
)
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

MAX_FAILED_CHALLENGES = 5
VIEW_MINUTES = 30
TTL_DAYS_MAX = 90


class LinkPurpose(StrEnum):
    RX_VIEW = "RX_VIEW"
    # M6d-P4 (billing R48, B7): a bill's receipt, with the same last-4 check and lockout.
    RECEIPT = "RECEIPT"


@dataclass(slots=True)
class PatientLink:
    id: UUID  # also the token's jti
    clinic_id: UUID
    patient_id: UUID
    # RX_VIEW: version 1 of the chain. RECEIPT: none (the bill is ``bill_id``).
    prescription_id: UUID | None
    purpose: LinkPurpose
    key_id: str
    expires_at: datetime
    revoked_at: datetime | None
    failed_challenges: int
    locked_at: datetime | None
    open_count: int
    last_opened_at: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    # M6d-P4: the receipt link's bill.
    bill_id: UUID | None = None

    @property
    def resource_id(self) -> UUID:
        """What the token's ``rid`` names: the prescription chain or the bill."""
        resource = self.bill_id if self.purpose is LinkPurpose.RECEIPT else self.prescription_id
        assert resource is not None  # a CHECK ties each purpose to its column
        return resource

    @property
    def rx_id(self) -> UUID:
        """The chain of a prescription link; ``LinkInvalid`` for any other link."""
        if self.purpose is not LinkPurpose.RX_VIEW or self.prescription_id is None:
            raise LinkInvalid()
        return self.prescription_id

    @classmethod
    def create_receipt(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        bill_id: UUID,
        key_id: str,
        ttl_days: int,
        created_by: UUID,
        now: datetime,
    ) -> PatientLink:
        """M6d-P4 (R48): a bill's receipt link; the rules of a prescription link."""
        link = cls.create(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            prescription_id=bill_id,
            key_id=key_id,
            ttl_days=ttl_days,
            created_by=created_by,
            now=now,
        )
        link.prescription_id = None
        link.purpose = LinkPurpose.RECEIPT
        link.bill_id = bill_id
        return link

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        prescription_id: UUID,
        key_id: str,
        ttl_days: int,
        created_by: UUID,
        now: datetime,
    ) -> PatientLink:
        now = require_utc(now, "now")
        if not 1 <= ttl_days <= TTL_DAYS_MAX:
            raise InvalidValue("ttl_days", f"must be 1-{TTL_DAYS_MAX}")
        return cls(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            prescription_id=prescription_id,
            purpose=LinkPurpose.RX_VIEW,
            key_id=key_id,
            # Whole seconds: the token carries the expiry as seconds and must agree with the row.
            expires_at=(now + timedelta(days=ttl_days)).replace(microsecond=0),
            revoked_at=None,
            failed_challenges=0,
            locked_at=None,
            open_count=0,
            last_opened_at=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None

    @property
    def attempts_left(self) -> int:
        return MAX_FAILED_CHALLENGES - self.failed_challenges

    def check_usable(self, now: datetime) -> None:
        """Revoked or expired links show nothing (the lock is checked where it matters)."""
        if self.revoked_at is not None:
            raise LinkRevoked()
        if require_utc(now, "now") >= self.expires_at:
            raise LinkExpired()

    def check_unlocked(self) -> None:
        if self.is_locked:
            raise LinkLocked()

    def record_failure(self, now: datetime) -> int:
        """R10: count a wrong answer; the fifth locks the link. Returns the attempts left."""
        now = require_utc(now, "now")
        self.check_unlocked()
        self.failed_challenges += 1
        if self.failed_challenges >= MAX_FAILED_CHALLENGES:
            self.locked_at = now
        self.updated_at = now
        return self.attempts_left

    def record_open(self, now: datetime) -> None:
        """R13: a right answer clears the count and is one open."""
        self.record_success(now)
        self.open_count += 1
        self.last_opened_at = self.updated_at

    def record_success(self, now: datetime) -> None:
        """A right answer clears the count (also M6b-P1's portal check, which opens nothing)."""
        now = require_utc(now, "now")
        self.check_unlocked()
        self.failed_challenges = 0
        self.updated_at = now

    def reset(self, now: datetime) -> None:
        """Staff unlock a locked link (decision 6A)."""
        if not self.is_locked:
            raise LinkNotLocked()
        self.failed_challenges = 0
        self.locked_at = None
        self.updated_at = require_utc(now, "now")

    def revoke(self, now: datetime) -> None:
        now = require_utc(now, "now")
        if self.revoked_at is None:
            self.revoked_at = now
            self.updated_at = now

    def view_expiry(self, now: datetime) -> datetime:
        """When a view opened now ends: 30 minutes, never past the link's own expiry."""
        return min(require_utc(now, "now") + timedelta(minutes=VIEW_MINUTES), self.expires_at)
