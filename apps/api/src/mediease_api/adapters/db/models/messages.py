"""Outbound messages (M5-P2, migration 0015, docs/DATA_MODEL.md ``messages``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, TenantOwned, Timestamps, enum_check
from mediease_api.domain.messaging.message import Channel, MessageStatus, SourceType
from mediease_api.domain.patients.patient import Language


class MessageRow(TenantOwned, Timestamps, Base):
    """One message to a patient; written before the provider call (spec R6)."""

    __tablename__ = "messages"
    __table_args__ = (
        enum_check("channel", Channel),
        enum_check("status", MessageStatus),
        enum_check("language", Language),
        enum_check("source_type", SourceType),
        CheckConstraint("template_version >= 1", name="template_version_positive"),
        # Accepted messages carry the provider's ID and the time; only they do.
        CheckConstraint(
            "(status IN ('SENT', 'DELIVERED', 'READ'))"
            " = (sent_at IS NOT NULL AND provider_message_id IS NOT NULL)",
            name="sent_has_provider_id",
        ),
        CheckConstraint(
            "(status = 'FAILED') = (failed_at IS NOT NULL AND error_code IS NOT NULL)",
            name="failed_has_code",
        ),
        CheckConstraint(
            "sending_started_at IS NULL OR status = 'QUEUED'", name="started_only_queued"
        ),
        Index("ix_messages_clinic_id_patient_id", "clinic_id", "patient_id"),
        Index(
            "ix_messages_clinic_id_source_type_source_id", "clinic_id", "source_type", "source_id"
        ),
    )

    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id"))
    source_type: Mapped[str] = mapped_column(Text)
    source_id: Mapped[UUID]
    channel: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text)
    template_key: Mapped[str] = mapped_column(Text)
    template_version: Mapped[int] = mapped_column(SmallInteger)
    language: Mapped[str] = mapped_column(Text)
    # Non-clinical values only, the signed link stored as "[link]" (R8, decision 5A).
    variables: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Fernet ciphertext (decision 1A); the key is MESSAGING_PHONE_KEYS, never in the database.
    to_phone_encrypted: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(Text, unique=True)
    cost_paise: Mapped[int | None] = mapped_column(BigInteger)
    request_id: Mapped[str | None] = mapped_column(Text)
    # The job that last tried it; no foreign key, finished jobs are purged after 30 days.
    job_id: Mapped[UUID | None]
    sending_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
