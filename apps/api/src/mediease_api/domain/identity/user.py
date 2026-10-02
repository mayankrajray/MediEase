"""User — a person who can sign in. Not tenant-owned: one user can work at several clinics.

A user is identified by an email address, a phone number or both (spec R1:
either can be the sign-in identifier). Platform ops staff are users with
``is_platform_ops`` and, by default, no clinic membership (R10).

Credentials and lockout state arrive with sign-in in M1-P2.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import required_text
from mediease_api.domain.shared.time import require_utc


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


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
        )

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
