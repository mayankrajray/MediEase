"""Patient accounts, their sessions and Google identities (migration 0020, M6a-P3, ADR-0015).

None of these is tenant data: a patient account is global to MediEase and holds no clinic data
until a clinic links it (M6b). Kept apart from ``users`` and ``refresh_tokens`` on purpose.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, Timestamps, enum_check
from mediease_api.domain.identity.email_token import EmailTokenPurpose
from mediease_api.domain.identity.external import IdentityProvider
from mediease_api.domain.portal.account import AccountStatus, SignInMethod


class PatientAccountRow(Keyed, Timestamps, Base):
    __tablename__ = "patient_accounts"
    __table_args__ = (
        enum_check("sign_in_method", SignInMethod),
        enum_check("status", AccountStatus),
        CheckConstraint("email = lower(email)", name="email_lower_case"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_non_negative"),
        # A password account has a hash and a Google account never does.
        CheckConstraint(
            "(sign_in_method = 'PASSWORD') = (password_hash IS NOT NULL)",
            name="password_matches_method",
        ),
        # The sign-in identifier: one password account per email. Google accounts are matched by
        # their identity's sub and may share an email with a password account (never merged).
        Index(
            "uq_patient_accounts_password_email",
            "email",
            unique=True,
            postgresql_where=text("sign_in_method = 'PASSWORD'"),
        ),
    )

    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sign_in_method: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    failed_login_count: Mapped[int] = mapped_column(server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientRefreshTokenRow(Keyed, Timestamps, Base):
    """One portal refresh token; the same lifecycle as ``refresh_tokens`` (M1-P2)."""

    __tablename__ = "patient_refresh_tokens"
    __table_args__ = (
        Index("ix_patient_refresh_tokens_family_id", "family_id"),
        Index("ix_patient_refresh_tokens_account_id", "account_id"),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id"))
    family_id: Mapped[UUID] = mapped_column()
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("patient_refresh_tokens.id"))


class ExternalIdentityRow(Keyed, Base):
    """A Google ``sub`` linked to exactly one staff user or one patient account (decision 4)."""

    __tablename__ = "external_identities"
    __table_args__ = (
        enum_check("provider", IdentityProvider),
        CheckConstraint(
            "(user_id IS NULL) <> (patient_account_id IS NULL)", name="exactly_one_owner"
        ),
        # One staff link and one patient link per provider subject, at most.
        Index(
            "uq_external_identities_staff_subject",
            "provider",
            "subject",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        Index(
            "uq_external_identities_patient_subject",
            "provider",
            "subject",
            unique=True,
            postgresql_where=text("patient_account_id IS NOT NULL"),
        ),
        Index("ix_external_identities_user_id", "user_id"),
        Index("ix_external_identities_patient_account_id", "patient_account_id"),
    )

    provider: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    patient_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("patient_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EmailTokenRow(Keyed, Base):
    """A single-use verification or reset token, stored as a digest (migration 0021, M6a-P4)."""

    __tablename__ = "email_tokens"
    __table_args__ = (
        enum_check("purpose", EmailTokenPurpose),
        CheckConstraint(
            "(user_id IS NULL) <> (patient_account_id IS NULL)", name="exactly_one_owner"
        ),
        CheckConstraint("email = lower(email)", name="email_lower_case"),
        Index("ix_email_tokens_user_id", "user_id"),
        Index("ix_email_tokens_patient_account_id", "patient_account_id"),
        Index("ix_email_tokens_expires_at", "expires_at"),
    )

    purpose: Mapped[str] = mapped_column(Text)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    patient_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("patient_accounts.id"))
    email: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
