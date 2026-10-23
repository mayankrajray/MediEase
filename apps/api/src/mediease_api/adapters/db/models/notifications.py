"""In-app notifications and their preferences (M6a-P7, migration 0023, ADR-0017)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.notifications.notification import Channel, NotificationKind


class NotificationRow(TenantOwned, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        enum_check("kind", NotificationKind),
        # FR-NTF-06: one per recipient and event, however often the event is replayed.
        UniqueConstraint("clinic_id", "recipient_user_id", "event_key"),
        # The bell: a member's newest first, and their unread count.
        Index(
            "ix_notifications_clinic_id_recipient_user_id_created_at",
            "clinic_id",
            "recipient_user_id",
            text("created_at DESC"),
        ),
        Index("ix_notifications_created_at", "created_at"),
    )

    recipient_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(Text)
    event_key: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreferenceRow(TenantOwned, Timestamps, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        enum_check("kind", NotificationKind),
        enum_check("channel", Channel),
        UniqueConstraint("clinic_id", "user_id", "kind", "channel"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean)
