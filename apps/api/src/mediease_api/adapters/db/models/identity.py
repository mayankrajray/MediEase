"""Tables for users and clinic memberships (migration 0002, docs/DATA_MODEL.md "M1")."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, TenantOwned, Timestamps, enum_check
from mediease_api.domain.identity.membership import MembershipStatus, Role
from mediease_api.domain.identity.user import UserStatus


class UserRow(Keyed, Timestamps, Base):
    """A person who signs in. Not tenant-owned: memberships link users to clinics.

    Credentials and lockout columns are added with sign-in in M1-P2.
    """

    __tablename__ = "users"
    __table_args__ = (
        enum_check("status", UserStatus),
        CheckConstraint("email IS NOT NULL OR phone_e164 IS NOT NULL", name="email_or_phone"),
        # Emails are compared exactly; the domain lower-cases them, the database insists.
        CheckConstraint("email = lower(email)", name="email_lower_case"),
    )

    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    phone_e164: Mapped[str | None] = mapped_column(Text, unique=True)
    is_platform_ops: Mapped[bool] = mapped_column(server_default=text("false"))
    status: Mapped[str] = mapped_column(Text)


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
