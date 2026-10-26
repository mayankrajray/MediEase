"""Clinic subscriptions (M6d-P7, migration 0041, docs/DATA_MODEL.md "M6d — Plans").

Platform data: one row per clinic, keyed by the clinic. Read through
``SqlAlchemySubscriptionRepository`` (a reviewed exception in tests/tenancy: ops list every
clinic's plan, and a clinic's limit check locks its own row).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Timestamps, enum_check
from mediease_api.domain.subscriptions.subscription import Plan


class ClinicSubscriptionRow(Timestamps, Base):
    __tablename__ = "clinic_subscriptions"
    __table_args__ = (
        enum_check("plan", Plan),
        CheckConstraint(
            "(trial_started_at IS NULL) = (trial_ends_at IS NULL)", name="trial_together"
        ),
        CheckConstraint(
            "trial_ends_at IS NULL OR trial_ends_at = trial_started_at + interval '14 days'",
            name="trial_14_days",
        ),
        CheckConstraint("has_trial OR trial_started_at IS NULL", name="trial_only_if_owed"),
    )

    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinics.id"), primary_key=True)
    plan: Mapped[str] = mapped_column(Text)
    has_trial: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_changed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
