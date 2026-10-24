"""Patient account links and portal invites (M6b-P1, migration 0025, docs/DATA_MODEL.md "M6b").

Both are tenant tables: a link and an invite belong to the clinic whose record they name, and are
reached through scoped repositories. The one cross-clinic read (an account's active links, and
which clinic an invite digest belongs to) is ``SqlAlchemyPortalLookup``, a reviewed exception.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, enum_check
from mediease_api.domain.portal.link import LinkMethod, RevokedBy


class PatientAccountLinkRow(TenantOwned, Base):
    __tablename__ = "patient_account_links"
    __table_args__ = (
        enum_check("method", LinkMethod),
        enum_check("revoked_by", RevokedBy),
        CheckConstraint("(revoked_at IS NULL) = (revoked_by IS NULL)", name="revoked_together"),
        # Decision 1A: one active link per record, and one per account in a clinic.
        Index(
            "uq_patient_account_links_patient_active",
            "clinic_id",
            "patient_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "uq_patient_account_links_account_active",
            "clinic_id",
            "account_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # The portal scope: an account's active links in every clinic.
        Index(
            "ix_patient_account_links_account_id_active",
            "account_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id"))
    method: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(Text)


class PatientPortalInviteRow(TenantOwned, Base):
    """A single-use invite, stored as the SHA-256 digest of its secret (R1)."""

    __tablename__ = "patient_portal_invites"
    __table_args__ = (
        CheckConstraint("(used_at IS NULL) = (used_by_account_id IS NULL)", name="used_together"),
        CheckConstraint("used_at IS NULL OR superseded_at IS NULL", name="used_or_superseded"),
        # One pending invite per record: a new one supersedes the old first.
        Index(
            "uq_patient_portal_invites_patient_pending",
            "clinic_id",
            "patient_id",
            unique=True,
            postgresql_where=text("used_at IS NULL AND superseded_at IS NULL"),
        ),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("patient_accounts.id"))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
