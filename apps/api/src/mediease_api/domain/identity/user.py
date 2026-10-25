"""User — a person who can sign in. Not tenant-owned: one user can work at several clinics.

A user is identified by an email address, a phone number or both (spec R1:
either can be the sign-in identifier). Platform ops staff are users with
``is_platform_ops`` and, by default, no clinic membership (R10).

Credentials and lockout (FR-AUTH-01, FR-AUTH-04, spec R3): the domain stores
an opaque password hash (produced by the ``PasswordHasher`` port) and counts
consecutive failed sign-ins. The fifth failure locks the account for 15
minutes; a successful sign-in resets the count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import required_text
from mediease_api.domain.shared.time import require_utc

MAX_FAILED_SIGN_INS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class OpsRole(StrEnum):
    """M6c-P2 (milestone decision M3): what a MediEase staff member may do on the platform."""

    # Clinics, imports, schedules and costs (the ops console as it was before M6c).
    ADMIN = "OPS_ADMIN"
    # Clinic applications: take, check doctors, decide (FR-ONB-03).
    REVIEWER = "OPS_REVIEWER"


ALL_OPS_ROLES: frozenset[OpsRole] = frozenset(OpsRole)


@dataclass(slots=True)
class User:
    """A user. Build new ones with ``User.create``; the constructor rehydrates."""

    id: UUID
    full_name: str
    email: EmailAddress | None
    phone: PhoneNumber | None
    is_platform_ops: bool
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    # None until a password is set (an invited user cannot sign in yet).
    # Excluded from repr so a hash never reaches a log line or a traceback.
    password_hash: str | None = field(default=None, repr=False)
    failed_sign_in_count: int = 0
    locked_until: datetime | None = None
    last_signed_in_at: datetime | None = None
    # M6c-P2: empty for clinic staff; an ops user holds at least one.
    ops_roles: frozenset[OpsRole] = frozenset()

    def has_ops_role(self, role: OpsRole) -> bool:
        return self.is_platform_ops and role in self.ops_roles

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        full_name: str,
        now: datetime,
        email: EmailAddress | None = None,
        phone: PhoneNumber | None = None,
        is_platform_ops: bool = False,
        password_hash: str | None = None,
        ops_roles: frozenset[OpsRole] | None = None,
    ) -> User:
        if email is None and phone is None:
            raise InvalidValue("email", "an email address or a phone number is required")
        now = require_utc(now, "now")
        return cls(
            id=id,
            full_name=required_text(full_name, "full_name", max_length=200),
            email=email,
            phone=phone,
            is_platform_ops=is_platform_ops,
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            password_hash=password_hash,
            # An ops user created without roles gets both, as every ops user had before M6c.
            ops_roles=(
                frozenset()
                if not is_platform_ops
                else (ALL_OPS_ROLES if ops_roles is None else frozenset(ops_roles))
            ),
        )

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE

    def disable(self, *, now: datetime) -> None:
        """Rejected from the next request on (R7)."""
        if self.status is UserStatus.DISABLED:
            raise InvalidTransition("user", self.status, "disable")
        self.updated_at = require_utc(now, "now")
        self.status = UserStatus.DISABLED

    def enable(self, *, now: datetime) -> None:
        if self.status is UserStatus.ACTIVE:
            raise InvalidTransition("user", self.status, "enable")
        self.updated_at = require_utc(now, "now")
        self.status = UserStatus.ACTIVE

    # --- credentials and lockout ---------------------------------------------------------

    def set_password_hash(self, password_hash: str, *, now: datetime) -> None:
        """Store a new hash (first password, or a re-hash with stronger parameters)."""
        if not password_hash:
            raise InvalidValue("password_hash", "must not be empty")
        self.updated_at = require_utc(now, "now")
        self.password_hash = password_hash

    def is_locked(self, now: datetime) -> bool:
        """True while a lockout from too many failed sign-ins is in force (R3)."""
        now = require_utc(now, "now")
        return self.locked_until is not None and now < self.locked_until

    def record_failed_sign_in(self, *, now: datetime) -> bool:
        """Count a wrong password. Returns True when this failure locked the account.

        The count resets when the lock starts, so after the 15 minutes the user
        has a fresh set of attempts.
        """
        self.updated_at = require_utc(now, "now")
        self.failed_sign_in_count += 1
        if self.failed_sign_in_count < MAX_FAILED_SIGN_INS:
            return False
        self.failed_sign_in_count = 0
        self.locked_until = self.updated_at + LOCKOUT_DURATION
        return True

    def record_successful_sign_in(self, *, now: datetime) -> None:
        """A correct password resets the failure count and clears an expired lock (R3)."""
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
