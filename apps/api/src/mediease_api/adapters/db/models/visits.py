"""Visits and their addenda (M4-P1, migration 0009, docs/DATA_MODEL.md "M4").

Every column holding clinical text is never logged; repositories map rows to domain entities and
nothing outside ``adapters/db`` sees these classes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.visits.attachment import FILENAME_MAX, MAX_ATTACHMENT_BYTES
from mediease_api.domain.visits.visit import ADDENDUM_MAX, TEXT_LIMITS, VisitStatus


def _length(column: str, limit: int) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IS NULL OR char_length({column}) <= {limit}", name=f"{column}_length"
    )


class VisitRow(TenantOwned, Timestamps, Base):
    """The clinical record of one appointment (R1: one visit per appointment)."""

    __tablename__ = "visits"
    __table_args__ = (
        # "This patient's visits, newest first" (R2): the consultation history and the list.
        Index(
            "ix_visits_clinic_id_patient_id_started_at",
            "clinic_id",
            "patient_id",
            text("started_at DESC"),
            text("id DESC"),
        ),
        # M6a-P6 *My Patients*: "the patients this doctor has seen" (migration 0022).
        Index(
            "ix_visits_clinic_id_doctor_id_started_at",
            "clinic_id",
            "doctor_id",
            text("started_at DESC"),
        ),
        enum_check("status", VisitStatus),
        CheckConstraint(
            "(status = 'COMPLETED') = (completed_at IS NOT NULL)", name="completed_has_time"
        ),
        # R3: the lock is exactly 24 hours after completion.
        CheckConstraint(
            "(completed_at IS NULL AND locked_at IS NULL)"
            " OR locked_at = completed_at + interval '24 hours'",
            name="locked_after_24_hours",
        ),
        CheckConstraint("revision >= 1", name="revision_positive"),
        *(_length(column, limit) for column, limit in TEXT_LIMITS.items()),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    appointment_id: Mapped[UUID] = mapped_column(ForeignKey("appointments.id"), unique=True)
    status: Mapped[str] = mapped_column(Text)
    chief_complaint: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[str | None] = mapped_column(Text)
    diagnosis: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    vitals: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    revision: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class VisitAddendumRow(TenantOwned, Base):
    """Append-only: a database trigger refuses UPDATE, DELETE and TRUNCATE (R3)."""

    __tablename__ = "visit_addenda"
    __table_args__ = (
        Index("ix_visit_addenda_visit_id_created_at", "visit_id", "created_at"),
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {ADDENDUM_MAX}", name="body_length"),
    )

    visit_id: Mapped[UUID] = mapped_column(ForeignKey("visits.id"))
    author_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VisitAttachmentRow(TenantOwned, Base):
    """M6d-P6 (migration 0040): a report on a visit. The file is in blob storage under
    ``storage_key``; the name is clinical and never logged."""

    __tablename__ = "visit_attachments"
    __table_args__ = (
        Index("ix_visit_attachments_visit_id_uploaded_at", "visit_id", "uploaded_at"),
        # The portal's "reports shared with me" (R11).
        Index(
            "ix_visit_attachments_clinic_id_patient_id_shared_at",
            "clinic_id",
            "patient_id",
            "shared_at",
            postgresql_where=text("shared_at IS NOT NULL AND deleted_at IS NULL"),
        ),
        CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="content_type",
        ),
        CheckConstraint(
            f"size_bytes BETWEEN 1 AND {MAX_ATTACHMENT_BYTES}", name="size_bytes_range"
        ),
        CheckConstraint(
            f"char_length(filename) BETWEEN 1 AND {FILENAME_MAX}", name="filename_length"
        ),
        CheckConstraint("(shared_at IS NULL) = (shared_by IS NULL)", name="shared_together"),
        CheckConstraint("(deleted_at IS NULL) = (deleted_by IS NULL)", name="deleted_together"),
    )

    visit_id: Mapped[UUID] = mapped_column(ForeignKey("visits.id"))
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(Text)
    uploaded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shared_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
