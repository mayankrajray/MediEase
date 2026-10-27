"""Prescription uploads (M7b, migration 0042, docs/DATA_MODEL.md "M7b — Prescription uploads").

Platform data owned by a patient account: ``clinic_id`` is set only once an upload is verified,
so the table is not ``TenantOwned`` and no clinic read ever reaches it. Reached only through
``SqlAlchemyPrescriptionUploadRepository`` (a reviewed exception in tests/tenancy).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, Timestamps
from mediease_api.domain.uploads.upload import MAX_CHALLENGES, MAX_UPLOAD_BYTES

_STATES = "'QUARANTINED', 'SCANNING', 'EXTRACTING', 'NEEDS_CHALLENGE', 'VERIFIED', 'REJECTED'"
_FILE_STATES = "'QUARANTINED', 'SCANNING', 'EXTRACTING'"
_REJECTIONS = (
    "'UPL_INFECTED', 'UPL_SCAN_UNAVAILABLE', 'UPL_NO_IDENTIFIER', 'UPL_AMBIGUOUS',"
    " 'UPL_UNREADABLE', 'UPL_LOCKED', 'UPL_ABANDONED', 'UPL_EXPIRED', 'UPL_WITHDRAWN',"
    " 'UPL_FILE_MISSING'"
)


class PrescriptionUploadRow(Keyed, Timestamps, Base):
    __tablename__ = "prescription_uploads"
    __table_args__ = (
        Index(
            "ix_prescription_uploads_account_id_created_at", "account_id", text("created_at DESC")
        ),
        Index(
            "ix_prescription_uploads_unfinished",
            "created_at",
            postgresql_where=text("state NOT IN ('VERIFIED', 'REJECTED')"),
        ),
        Index("ix_prescription_uploads_created_at", "created_at"),
        CheckConstraint("source IN ('FILE', 'CODE')", name="source"),
        CheckConstraint(f"state IN ({_STATES})", name="state"),
        CheckConstraint("access IN ('OWN', 'REPRESENTATIVE')", name="access"),
        CheckConstraint(f"rejection_code IN ({_REJECTIONS})", name="rejection"),
        CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')", name="content_type"
        ),
        CheckConstraint(f"size_bytes BETWEEN 1 AND {MAX_UPLOAD_BYTES}", name="size_bytes_range"),
        CheckConstraint(
            f"failed_challenges BETWEEN 0 AND {MAX_CHALLENGES}", name="failed_challenges_range"
        ),
        CheckConstraint(
            "(source = 'FILE') = (content_type IS NOT NULL AND size_bytes IS NOT NULL"
            " AND sha256 IS NOT NULL)",
            name="file_described",
        ),
        CheckConstraint(
            f"quarantine_key IS NULL OR (source = 'FILE' AND state IN ({_FILE_STATES}))",
            name="file_only_while_checked",
        ),
        CheckConstraint(
            "(state = 'VERIFIED') = (clinic_id IS NOT NULL AND prescription_id IS NOT NULL"
            " AND access IS NOT NULL AND verified_at IS NOT NULL AND expires_at IS NOT NULL)",
            name="verified_is_complete",
        ),
        CheckConstraint("selected_id IS NULL OR state = 'VERIFIED'", name="selected_if_verified"),
        CheckConstraint(
            "(state = 'REJECTED') = (rejection_code IS NOT NULL)", name="rejected_has_code"
        ),
        CheckConstraint(
            "(state = 'NEEDS_CHALLENGE') = (candidate_id IS NOT NULL)",
            name="candidate_while_challenged",
        ),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(Text)
    quarantine_key: Mapped[str | None] = mapped_column(Text, unique=True)
    candidate_id: Mapped[UUID | None] = mapped_column()
    clinic_id: Mapped[UUID | None] = mapped_column(ForeignKey("clinics.id"))
    prescription_id: Mapped[UUID | None] = mapped_column(ForeignKey("prescriptions.id"))
    access: Mapped[str | None] = mapped_column(Text)
    selected_id: Mapped[UUID | None] = mapped_column(ForeignKey("prescriptions.id"))
    rejection_code: Mapped[str | None] = mapped_column(Text)
    failed_challenges: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
