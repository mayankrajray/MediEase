"""Patient links and public-route rate limits (M4-P5, migration 0013, docs/DATA_MODEL.md "M4")."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.links.link import MAX_FAILED_CHALLENGES, LinkPurpose


class PatientLinkRow(TenantOwned, Timestamps, Base):
    """One link per prescription chain (decision 1A); the token's ``jti`` is ``id``."""

    __tablename__ = "patient_links"
    __table_args__ = (
        enum_check("purpose", LinkPurpose),
        # One active link per chain; replacing revokes the old one first.
        Index(
            "uq_patient_links_prescription_id_active",
            "prescription_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # M6d-P4: one active receipt link per bill.
        Index(
            "uq_patient_links_bill_id_active",
            "bill_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # Each purpose names its own resource (M6d-P4).
        CheckConstraint(
            "(purpose = 'RX_VIEW') = (prescription_id IS NOT NULL)"
            " AND (purpose = 'RECEIPT') = (bill_id IS NOT NULL)",
            name="resource_of_purpose",
        ),
        Index("ix_patient_links_clinic_id_patient_id", "clinic_id", "patient_id"),
        CheckConstraint(
            f"failed_challenges BETWEEN 0 AND {MAX_FAILED_CHALLENGES}",
            name="failed_challenges_range",
        ),
        CheckConstraint(
            f"(locked_at IS NOT NULL) = (failed_challenges = {MAX_FAILED_CHALLENGES})",
            name="locked_at_five",
        ),
        CheckConstraint("open_count >= 0", name="open_count_positive"),
        CheckConstraint("key_id ~ '^[A-Za-z0-9_-]{1,16}$'", name="key_id_format"),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    # Version 1 of the chain; the page shows the latest issued version.
    prescription_id: Mapped[UUID | None] = mapped_column(ForeignKey("prescriptions.id"))
    # M6d-P4 (billing R48): a receipt link's bill.
    bill_id: Mapped[UUID | None] = mapped_column(ForeignKey("bills.id"))
    purpose: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_challenges: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    open_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class PublicRateLimitRow(Base):
    """Requests per one-minute window for a bucket (decision 4A). Not tenant data."""

    __tablename__ = "public_rate_limits"
    __table_args__ = (
        PrimaryKeyConstraint("bucket", "window_start"),
        Index("ix_public_rate_limits_window_start", "window_start"),
        CheckConstraint("hits >= 1", name="hits_positive"),
    )

    bucket: Mapped[str] = mapped_column(Text)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hits: Mapped[int] = mapped_column(Integer)
