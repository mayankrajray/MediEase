"""Prescriptions and their items (M4-P2, migration 0010, docs/DATA_MODEL.md "M4").

Clinical content: never logged. Issued versions are immutable in the database too: triggers in
migration 0010 refuse any change except the operational columns (spec R6, AC1).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.prescription import LinkDelivery, PrescriptionStatus
from mediease_api.domain.prescriptions.vocabulary import Frequency, Timing


def _length(column: str, limit: int, *, required: bool = False) -> CheckConstraint:
    rule = (
        f"char_length({column}) BETWEEN 1 AND {limit}"
        if required
        else f"{column} IS NULL OR char_length({column}) <= {limit}"
    )
    return CheckConstraint(rule, name=f"{column}_length")


class PrescriptionRow(TenantOwned, Timestamps, Base):
    """One version of a visit's prescription chain (decision 1A)."""

    __tablename__ = "prescriptions"
    __table_args__ = (
        UniqueConstraint("visit_id", "version"),
        # At most one draft per chain (decision 1A).
        Index(
            "uq_prescriptions_visit_id_draft",
            "visit_id",
            unique=True,
            postgresql_where=text("status = 'DRAFT'"),
        ),
        Index(
            "ix_prescriptions_clinic_id_patient_id_issued_at",
            "clinic_id",
            "patient_id",
            text("issued_at DESC"),
        ),
        enum_check("status", PrescriptionStatus),
        enum_check("language", Language),
        enum_check("link_delivery", LinkDelivery),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("(version = 1) = (supersedes_id IS NULL)", name="version_chain"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("layout_version >= 1", name="layout_version_positive"),
        # R5: an issued version carries everything that was printed and sent; a draft none of it.
        CheckConstraint(
            "status = 'DRAFT' OR (issued_at IS NOT NULL AND language IS NOT NULL"
            " AND doctor_snapshot IS NOT NULL AND clinic_snapshot IS NOT NULL"
            " AND link_delivery IS NOT NULL)",
            name="issued_is_complete",
        ),
        CheckConstraint(
            "status <> 'DRAFT' OR (issued_at IS NULL AND link_delivery IS NULL"
            " AND pdf_object_key IS NULL)",
            name="draft_is_unissued",
        ),
    )

    visit_id: Mapped[UUID] = mapped_column(ForeignKey("visits.id"))
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    version: Mapped[int] = mapped_column(SmallInteger)
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("prescriptions.id"))
    status: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    advice: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    follow_up_date: Mapped[date | None] = mapped_column(Date)
    language: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    doctor_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    clinic_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    pdf_object_key: Mapped[str | None] = mapped_column(Text)
    link_delivery: Mapped[str | None] = mapped_column(Text)
    link_delivery_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M4-P3: the template the body came from; a plain ID (deleting a template touches nothing).
    template_id: Mapped[UUID | None] = mapped_column()
    # M4-P5 (migration 0013): the printed layout fixed at issue.
    layout_version: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class PrescriptionItemRow(TenantOwned, Base):
    """One medicine line. Writable only while its prescription is a draft (trigger)."""

    __tablename__ = "prescription_items"
    __table_args__ = (
        UniqueConstraint("prescription_id", "position"),
        # M4-P3: start-of-name suggestions ignoring case (the M2 pattern, no extension).
        Index(
            "ix_prescription_items_clinic_id_medicine_name",
            "clinic_id",
            text("lower(medicine_name) text_pattern_ops"),
        ),
        enum_check("frequency", Frequency),
        enum_check("timing", Timing),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(
            "(frequency IS NOT DISTINCT FROM 'CUSTOM') = (frequency_text IS NOT NULL)",
            name="custom_frequency_text",
        ),
        CheckConstraint(
            "duration_days IS NULL OR duration_days BETWEEN 1 AND 365", name="duration_days_range"
        ),
        _length("medicine_name", 200, required=True),
        _length("form", 100),
        _length("strength", 100),
        _length("dose", 100),
        _length("frequency_text", 100),
        _length("quantity", 100),
        _length("warnings", 500),
        _length("notes", 1000),
    )

    prescription_id: Mapped[UUID] = mapped_column(ForeignKey("prescriptions.id"))
    position: Mapped[int] = mapped_column(SmallInteger)
    medicine_name: Mapped[str] = mapped_column(Text)
    form: Mapped[str | None] = mapped_column(Text)
    strength: Mapped[str | None] = mapped_column(Text)
    dose: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str | None] = mapped_column(Text)
    frequency_text: Mapped[str | None] = mapped_column(Text)
    timing: Mapped[str | None] = mapped_column(Text)
    duration_days: Mapped[int | None] = mapped_column(SmallInteger)
    quantity: Mapped[str | None] = mapped_column(Text)
    preparation: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    storage: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    warnings: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # M4-P3: the favourite the line came from; a plain ID, as template_id.
    favourite_id: Mapped[UUID | None] = mapped_column()
