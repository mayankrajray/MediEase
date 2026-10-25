"""Patient notifications and their preferences (migration 0031, M6b-P6; portal spec R55-R63).

``patient_notifications`` is tenant data: one row per notification, each for one account. The
unique ``(account_id, event_key)`` is what makes delivery idempotent (R58). No text is stored.
``patient_notification_preferences`` belongs to the account (no clinic), like the account itself.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, TenantOwned, Timestamps, enum_check
from mediease_api.domain.portal.notifications import PatientChannel, PatientNotificationKind


class PatientNotificationRow(TenantOwned, Base):
    __tablename__ = "patient_notifications"
    __table_args__ = (
        enum_check("kind", PatientNotificationKind),
        # R58: one per account and event, whatever the replays or concurrent workers.
        UniqueConstraint("account_id", "event_key"),
        Index(
            "ix_patient_notifications_account_id_created_at",
            "account_id",
            text("created_at DESC"),
        ),
        Index("ix_patient_notifications_created_at", "created_at"),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id"))
    kind: Mapped[str] = mapped_column(Text)
    event_key: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[UUID]
    link: Mapped[str] = mapped_column(Text)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PatientNotificationPreferenceRow(Keyed, Timestamps, Base):
    __tablename__ = "patient_notification_preferences"
    __table_args__ = (
        enum_check("kind", PatientNotificationKind),
        enum_check("channel", PatientChannel),
        UniqueConstraint("account_id", "kind", "channel"),
    )

    account_id: Mapped[UUID] = mapped_column(ForeignKey("patient_accounts.id"))
    kind: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean)
