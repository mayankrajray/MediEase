"""Single-use email tokens: verify an email, reset a password (M6a-P4, ADR-0016 decision 5).

A token belongs to exactly one staff user or one patient account and was sent to one address.
Only a digest of its value is stored; the value exists in the email and nowhere else (decision
4: the worker makes it at send time, so not even the job holds it).

States, derived rather than stored::

    ACTIVE      usable: not used, not superseded, not expired
    USED        already used once
    SUPERSEDED  a newer token of the same purpose was sent to the same account
    EXPIRED     past expires_at (24 hours to verify, 30 minutes to reset)

A token is also refused when the account's email is no longer the address it was sent to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.time import require_utc


class EmailTokenPurpose(StrEnum):
    VERIFY_EMAIL = "VERIFY_EMAIL"
    RESET_PASSWORD = "RESET_PASSWORD"


LIFETIMES: dict[EmailTokenPurpose, timedelta] = {
    EmailTokenPurpose.VERIFY_EMAIL: timedelta(hours=24),
    EmailTokenPurpose.RESET_PASSWORD: timedelta(minutes=30),
}


class EmailTokenState(StrEnum):
    ACTIVE = "ACTIVE"
    USED = "USED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class TokenInvalid(DomainError):
    """Unknown, used, superseded or sent to another address: one answer for all of them."""

    code = "AUTH_TOKEN_INVALID"

    def __init__(self) -> None:
        super().__init__("This link is not valid any more. Ask for a new one.")


class TokenExpired(DomainError):
    code = "AUTH_TOKEN_EXPIRED"

    def __init__(self) -> None:
        super().__init__("This link has expired. Ask for a new one.")


@dataclass(slots=True)
class EmailToken:
    """Build with ``EmailToken.issue``; the constructor rehydrates."""

    id: UUID
    purpose: EmailTokenPurpose
    user_id: UUID | None
    patient_account_id: UUID | None
    email: EmailAddress
    token_hash: str = field(repr=False)
    expires_at: datetime
    created_at: datetime
    used_at: datetime | None = None
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        if (self.user_id is None) == (self.patient_account_id is None):
            raise InvalidValue("user_id", "exactly one of user_id and patient_account_id")

    @classmethod
    def issue(
        cls,
        *,
        id: UUID,
        purpose: EmailTokenPurpose,
        email: EmailAddress,
        token_hash: str,
        now: datetime,
        user_id: UUID | None = None,
        patient_account_id: UUID | None = None,
    ) -> EmailToken:
        if not token_hash:
            raise InvalidValue("token_hash", "must not be empty")
        now = require_utc(now, "now")
        return cls(
            id=id,
            purpose=purpose,
            user_id=user_id,
            patient_account_id=patient_account_id,
            email=email,
            token_hash=token_hash,
            expires_at=now + LIFETIMES[purpose],
            created_at=now,
        )

    @property
    def is_for_staff(self) -> bool:
        return self.user_id is not None

    def state(self, now: datetime) -> EmailTokenState:
        if self.used_at is not None:
            return EmailTokenState.USED
        if self.superseded_at is not None:
            return EmailTokenState.SUPERSEDED
        if require_utc(now, "now") >= self.expires_at:
            return EmailTokenState.EXPIRED
        return EmailTokenState.ACTIVE

    def check_usable(
        self, *, purpose: EmailTokenPurpose, email: EmailAddress, now: datetime
    ) -> None:
        """``TokenInvalid`` or ``TokenExpired`` unless this token may be used now, for this."""
        if self.purpose is not purpose or self.email != email:
            raise TokenInvalid()
        state = self.state(now)
        if state is EmailTokenState.EXPIRED:
            raise TokenExpired()
        if state is not EmailTokenState.ACTIVE:
            raise TokenInvalid()

    def use(self, *, now: datetime) -> None:
        if self.state(now) is not EmailTokenState.ACTIVE:
            raise TokenInvalid()
        self.used_at = require_utc(now, "now")
