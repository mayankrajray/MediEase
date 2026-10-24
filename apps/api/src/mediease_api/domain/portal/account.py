"""PatientAccount — a person who signs in to the patient portal (FR-PRT-01, ADR-0015).

Kept apart from staff ``User``s on purpose (decision 1): a patient account has no memberships, so
no change to staff code can ever grant it a clinic route. The same person may hold a staff user
and a patient account; they are unrelated rows.

An account is global to MediEase and holds no clinic data until a clinic links it (M6b,
FR-PRT-06). Two ways in:

- **Email and password** (``PASSWORD``): the email starts unverified (``email_verified_at`` is
  null) until M6a-P4 can send a verification email (FR-AUTH-08). Such an email is unique among
  password accounts, so the sign-in identifier is unambiguous.
- **Google** (``GOOGLE``): created at the first Google sign-in, matched by Google's ``sub`` after
  that (``ExternalIdentity``), and verified from the start because Google verified the address.

The two are never merged, even with the same address (decision 5): an unverified address must
not let its registrant claim someone else's account or, later, their linked records.

Lockout is the staff rule (FR-AUTH-04): five consecutive wrong passwords lock the account for 15
minutes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.identity.user import LOCKOUT_DURATION, MAX_FAILED_SIGN_INS
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.text import required_text
from mediease_api.domain.shared.time import require_utc

MAX_NAME_LENGTH = 200


class SignInMethod(StrEnum):
    """How the account was created, and so how it signs in."""

    PASSWORD = "PASSWORD"
    GOOGLE = "GOOGLE"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class EmailTaken(DomainError):
    """A password account with this email already exists (decision 7: accepted, rate limited)."""

    code = "PRT_EMAIL_TAKEN"

    def __init__(self) -> None:
        super().__init__("An account with this email already exists. Sign in instead.")


@dataclass(slots=True)
class PatientAccount:
    """Build new accounts with ``with_password`` or ``from_google``; the constructor rehydrates."""

    id: UUID
    full_name: str
    email: EmailAddress
    sign_in_method: SignInMethod
    status: AccountStatus
    created_at: datetime
    updated_at: datetime
    # Null until the address is proved (Google at once; password accounts from M6a-P4).
    email_verified_at: datetime | None = None
    # Only for PASSWORD accounts; excluded from repr so a hash never reaches a log line.
    password_hash: str | None = field(default=None, repr=False)
    failed_sign_in_count: int = 0
    locked_until: datetime | None = None
    last_signed_in_at: datetime | None = None
    # M6b-P2 (FR-PRT-04, NFR-11): the portal's language, chosen by the person (decision 2A).
    language: Language = Language.EN

    @classmethod
    def with_password(
        cls,
        *,
        id: UUID,
        full_name: str,
        email: EmailAddress,
        password_hash: str,
        now: datetime,
        language: Language = Language.EN,
    ) -> PatientAccount:
        if not password_hash:
            raise InvalidValue("password_hash", "must not be empty")
        now = require_utc(now, "now")
        return cls(
            id=id,
            full_name=required_text(full_name, "full_name", max_length=MAX_NAME_LENGTH),
            email=email,
            sign_in_method=SignInMethod.PASSWORD,
            status=AccountStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            password_hash=password_hash,
            language=language,
        )

    @classmethod
    def from_google(
        cls,
        *,
        id: UUID,
        full_name: str,
        email: EmailAddress,
        now: datetime,
        language: Language = Language.EN,
    ) -> PatientAccount:
        """Google proved the address (``email_verified`` in the ID token), so it is verified."""
        now = require_utc(now, "now")
        return cls(
            id=id,
            full_name=required_text(full_name, "full_name", max_length=MAX_NAME_LENGTH),
            email=email,
            sign_in_method=SignInMethod.GOOGLE,
            status=AccountStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            email_verified_at=now,
            language=language,
        )

    @property
    def is_active(self) -> bool:
        return self.status is AccountStatus.ACTIVE

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    # --- credentials and lockout (the staff rules, FR-AUTH-04) ----------------------------

    def set_password_hash(self, password_hash: str, *, now: datetime) -> None:
        """A re-hash with stronger parameters. Google accounts have no password in M6a."""
        if self.sign_in_method is not SignInMethod.PASSWORD:
            raise InvalidValue("password_hash", "this account signs in with Google")
        if not password_hash:
            raise InvalidValue("password_hash", "must not be empty")
        self.updated_at = require_utc(now, "now")
        self.password_hash = password_hash

    def is_locked(self, now: datetime) -> bool:
        now = require_utc(now, "now")
        return self.locked_until is not None and now < self.locked_until

    def record_failed_sign_in(self, *, now: datetime) -> bool:
        """Count a wrong password. Returns True when this failure locked the account."""
        self.updated_at = require_utc(now, "now")
        self.failed_sign_in_count += 1
        if self.failed_sign_in_count < MAX_FAILED_SIGN_INS:
            return False
        self.failed_sign_in_count = 0
        self.locked_until = self.updated_at + LOCKOUT_DURATION
        return True

    def record_successful_sign_in(self, *, now: datetime) -> None:
        now = require_utc(now, "now")
        self.updated_at = now
        self.last_signed_in_at = now
        self.failed_sign_in_count = 0
        self.locked_until = None

    def clear_lockout(self, *, now: datetime) -> None:
        """A completed password reset (M6a-P4) starts the failure count afresh."""
        self.updated_at = require_utc(now, "now")
        self.failed_sign_in_count = 0
        self.locked_until = None

    def set_language(self, language: Language, *, now: datetime) -> bool:
        """Change the portal's language. Returns False when it already was this one."""
        if self.language is language:
            return False
        self.language = language
        self.updated_at = require_utc(now, "now")
        return True

    def verify_email(self, *, now: datetime) -> bool:
        """Mark the address proved. Returns False when it already was (idempotent)."""
        if self.email_verified_at is not None:
            return False
        self.email_verified_at = self.updated_at = require_utc(now, "now")
        return True
