"""What the auth use cases return. Plain data: delivery decides what goes where.

``SessionTokens`` holds secrets; delivery puts them in cookies and never in a
response body (spec R4). Their ``repr`` hides the values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mediease_api.domain.identity.access import ClinicAccess
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.user import User


@dataclass(frozen=True, slots=True)
class UserView:
    id: UUID
    full_name: str
    email: str | None
    phone_e164: str | None
    is_platform_ops: bool

    @classmethod
    def of(cls, user: User) -> UserView:
        return cls(
            id=user.id,
            full_name=user.full_name,
            email=user.email.value if user.email else None,
            phone_e164=user.phone.e164 if user.phone else None,
            is_platform_ops=user.is_platform_ops,
        )


@dataclass(frozen=True, slots=True)
class MembershipView:
    membership_id: UUID
    clinic_id: UUID
    clinic_name: str
    role: Role

    @classmethod
    def of(cls, access: ClinicAccess) -> MembershipView:
        return cls(
            membership_id=access.membership_id,
            clinic_id=access.clinic_id,
            clinic_name=access.clinic_name,
            role=access.role,
        )


@dataclass(frozen=True, slots=True)
class SessionTokens:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime

    def __repr__(self) -> str:
        return (
            "SessionTokens(<redacted>, "
            f"access_expires_at={self.access_expires_at.isoformat()}, "
            f"refresh_expires_at={self.refresh_expires_at.isoformat()})"
        )


@dataclass(frozen=True, slots=True)
class SessionResult:
    """A signed-in session: who, where they can work, and the new tokens."""

    user: UserView
    memberships: tuple[MembershipView, ...]
    tokens: SessionTokens
