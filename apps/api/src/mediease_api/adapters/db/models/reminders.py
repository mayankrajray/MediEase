"""Follow-up reminders (M5-P4, migration 0017, docs/DATA_MODEL.md ``reminders``)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.reminders.reminder import ReminderKind, ReminderSource, ReminderStatus


class ReminderRow(TenantOwned, Timestamps, Base):
    __tablename__ = "reminders"
    __table_args__ = (
        enum_check("kind", ReminderKind),
        enum_check("source", ReminderSource),
        enum_check("status", ReminderStatus),
        CheckConstraint("revision >= 1", name="revision_positive"),
        # A prescription's reminder names its chain (version 1); a manual one names nothing.
        CheckConstraint("(source = 'PRESCRIPTION') = (source_id IS NOT NULL)", name="source_id"),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)", name="cancelled_has_time"
        ),
        # Decision 1A: one scheduled reminder per prescription chain.
        Index(
            "uq_reminders_source_id_scheduled",
            "source_id",
            unique=True,
            postgresql_where=text("status = 'SCHEDULED'"),
        ),
        Index("ix_reminders_clinic_id_patient_id", "clinic_id", "patient_id"),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    doctor_id: Mapped[UUID] = mapped_column(ForeignKey("doctors.id"))
    kind: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("prescriptions.id"))
    follow_up_date: Mapped[date] = mapped_column(Date)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(SmallInteger)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    cancelled_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
