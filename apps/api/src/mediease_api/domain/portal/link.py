"""Links between a patient account and one clinic's patient record (M6b-P1; FR-PRT-02, 06).

Spec ``docs/specs/patient-portal.md`` R1-R9; design decisions 1A-3A, 7A.

**A link** (``PatientAccountLink``) lets one account read one clinic's record of one patient. It
is made only from proof the clinic gave the patient (R7): a clinic invite (``INVITE``) or the
prescription link's last-4 check (``RX_LINK``); an accepted booking request adds ``BOOKING`` in
P5. At most one active link per record and one per account per clinic (decision 1A; partial
unique indexes back both). Revoking ends it at once and keeps the row as history (R8).

**An invite** (``PatientPortalInvite``) is a single-use secret shown once to the clinic, stored
as a digest, valid seven days. A new invite for the record supersedes the old one. An unknown,
used, superseded or expired invite is one answer, ``PRT_INVITE_INVALID`` (R2), so a guessed or
stale token learns nothing. The domain never reads a clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.errors import DomainError
from mediease_api.domain.shared.time import require_utc

INVITE_TTL = timedelta(days=7)


class LinkMethod(StrEnum):
    """How the link was made (decision 1A). ``BOOKING``: an accepted booking request (M6b-P5,
    FR-PRT-06 a)."""

    INVITE = "INVITE"
    RX_LINK = "RX_LINK"
    BOOKING = "BOOKING"


class RevokedBy(StrEnum):
    PATIENT = "PATIENT"
    STAFF = "STAFF"


class PortalInviteInvalid(DomainError):
    """R2: unknown, used, superseded or expired; the same answer for each."""

    code = "PRT_INVITE_INVALID"

    def __init__(self) -> None:
        super().__init__("This invitation is no longer valid. Ask the clinic for a new one.")


class AlreadyLinked(DomainError):
    """R4: the record has another account, or the account already has a record in the clinic."""

    code = "PRT_ALREADY_LINKED"

    def __init__(self) -> None:
        super().__init__("These records can't be linked to this account. Contact the clinic.")


class UnverifiedAccount(DomainError):
    """R5: linking by a prescription link needs a verified email (or Google)."""

    code = "PRT_UNVERIFIED_ACCOUNT"

    def __init__(self) -> None:
        super().__init__("Verify your email address first, then try again.")


@dataclass(slots=True)
class PatientAccountLink:
    id: UUID
    clinic_id: UUID
    patient_id: UUID
    account_id: UUID
    method: LinkMethod
    created_at: datetime
    # The staff member behind an invite; null for the patient's own proof (a prescription link).
    created_by_user_id: UUID | None
    revoked_at: datetime | None = None
    revoked_by: RevokedBy | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        account_id: UUID,
        method: LinkMethod,
        created_by_user_id: UUID | None,
        now: datetime,
    ) -> PatientAccountLink:
        return cls(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            account_id=account_id,
            method=method,
            created_at=require_utc(now, "now"),
            created_by_user_id=created_by_user_id,
        )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self, by: RevokedBy, now: datetime) -> bool:
        """End the link (R8). Returns False when it already was (idempotent)."""
        if self.revoked_at is not None:
            return False
        self.revoked_at = require_utc(now, "now")
        self.revoked_by = by
        return True


def check_can_link(
    *, record_link: PatientAccountLink | None, account_link: PatientAccountLink | None
) -> None:
    """R4: the record's active link and the account's active link in that clinic must not exist."""
    if record_link is not None or account_link is not None:
        raise AlreadyLinked()


@dataclass(slots=True)
class PatientPortalInvite:
    id: UUID
    clinic_id: UUID
    patient_id: UUID
    token_hash: str
    expires_at: datetime
    created_by: UUID
    created_at: datetime
    used_at: datetime | None = None
    used_by_account_id: UUID | None = None
    superseded_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        token_hash: str,
        created_by: UUID,
        now: datetime,
    ) -> PatientPortalInvite:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            token_hash=token_hash,
            expires_at=now + INVITE_TTL,
            created_by=created_by,
            created_at=now,
        )

    @property
    def is_pending(self) -> bool:
        """Neither used nor superseded (it may still have expired)."""
        return self.used_at is None and self.superseded_at is None

    def is_usable(self, now: datetime) -> bool:
        return self.is_pending and require_utc(now, "now") < self.expires_at

    def check_usable(self, now: datetime) -> None:
        if not self.is_usable(now):
            raise PortalInviteInvalid()

    def use(self, account_id: UUID, now: datetime) -> None:
        """R3: once only; a used invite is ``PRT_INVITE_INVALID`` from then on."""
        self.check_usable(now)
        self.used_at = require_utc(now, "now")
        self.used_by_account_id = account_id

    def supersede(self, now: datetime) -> bool:
        """A new invite replaces this one. Returns False when it was already used or replaced."""
        if not self.is_pending:
            return False
        self.superseded_at = require_utc(now, "now")
        return True
