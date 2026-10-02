"""Tables for users and clinic memberships (migration 0002, docs/DATA_MODEL.md "M1")."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, TenantOwned, Timestamps, enum_check
from mediease_api.domain.identity.membership import MembershipStatus, Role
from mediease_api.domain.identity.user import UserStatus


class UserRow(Keyed, Timestamps, Base):
    """A person who signs in. Not tenant-owned: memberships link users to clinics."""

    __tablename__ = "users"
    __table_args__ = (
        enum_check("status", UserStatus),
        CheckConstraint("email IS NOT NULL OR phone_e164 IS NOT NULL", name="email_or_phone"),
        # Emails are compared exactly; the domain lower-cases them, the database insists.
        CheckConstraint("email = lower(email)", name="email_lower_case"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
    )

    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    phone_e164: Mapped[str | None] = mapped_column(Text, unique=True)
    is_platform_ops: Mapped[bool] = mapped_column(server_default=text("false"))
    status: Mapped[str] = mapped_column(Text)
    # M1-P2. Null until a password is set (invited users cannot sign in yet).
    password_hash: Mapped[str | None] = mapped_column(Text)
    failed_login_count: Mapped[int] = mapped_column(server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClinicMembershipRow(TenantOwned, Timestamps, Base):
    """A user's single role at one clinic."""

    __tablename__ = "clinic_memberships"
    __table_args__ = (
        # I2: at most one membership per user per clinic; also the clinic_id index.
        UniqueConstraint("clinic_id", "user_id"),
        # "Which clinics does this user belong to?" (sign-in and clinic switcher, M1-P2/P3).
        Index("ix_clinic_memberships_user_id", "user_id"),
        enum_check("role", Role),
        enum_check("status", MembershipStatus),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)


class RefreshTokenRow(Keyed, Timestamps, Base):
    """One refresh token; a family is every token descended from one sign-in (M1-P2).

    Owned by a user, not a clinic. Only the SHA-256 digest of the token is stored.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    family_id: Mapped[UUID] = mapped_column()
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("refresh_tokens.id"))
