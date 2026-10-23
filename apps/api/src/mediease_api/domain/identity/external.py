"""ExternalIdentity — a Google account linked to a staff user or a patient account (ADR-0015).

Decision 4: after the first sign-in a person is matched by the provider's stable subject
(``sub``) only, never by email again, so an address that moves at Google does not move access
with it. One identity row points at exactly one of the two kinds of account; the same Google
account may hold one row of each kind, because the same person may be staff and a patient.

Staff rows are only ever created for an existing, active staff user whose email equals Google's
verified email: Google never creates staff access (FR-AUTH-07).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

MAX_SUBJECT_LENGTH = 255


class IdentityProvider(StrEnum):
    GOOGLE = "GOOGLE"


@dataclass(slots=True)
class ExternalIdentity:
    """Build with ``for_staff`` or ``for_patient``; the constructor rehydrates."""

    id: UUID
    provider: IdentityProvider
    subject: str
    user_id: UUID | None
    patient_account_id: UUID | None
    created_at: datetime
    last_used_at: datetime

    def __post_init__(self) -> None:
        if (self.user_id is None) == (self.patient_account_id is None):
            raise InvalidValue("user_id", "exactly one of user_id and patient_account_id")
        if not self.subject or len(self.subject) > MAX_SUBJECT_LENGTH:
            raise InvalidValue("subject", f"must be 1-{MAX_SUBJECT_LENGTH} characters")

    @classmethod
    def for_staff(
        cls, *, id: UUID, provider: IdentityProvider, subject: str, user_id: UUID, now: datetime
    ) -> ExternalIdentity:
        now = require_utc(now, "now")
        return cls(id, provider, subject, user_id, None, now, now)

    @classmethod
    def for_patient(
        cls,
        *,
        id: UUID,
        provider: IdentityProvider,
        subject: str,
        patient_account_id: UUID,
        now: datetime,
    ) -> ExternalIdentity:
        now = require_utc(now, "now")
        return cls(id, provider, subject, None, patient_account_id, now, now)

    def record_use(self, *, now: datetime) -> None:
        self.last_used_at = require_utc(now, "now")
