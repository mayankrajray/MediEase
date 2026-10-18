"""Outbound messages (M5-P2, migration 0015, docs/DATA_MODEL.md ``messages``)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, TenantOwned, Timestamps, enum_check
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
        # Accepted messages carry the provider's ID and the time (a later FAILED keeps them).
        CheckConstraint(
            "status NOT IN ('SENT', 'DELIVERED', 'READ')"
            " OR (sent_at IS NOT NULL AND provider_message_id IS NOT NULL)",
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
    # M5-P3: the provider's pricing category from the status webhook (P5's cost ledger).
    pricing_category: Mapped[str | None] = mapped_column(Text)


class WebhookEventRow(Keyed, Base):
    """A provider webhook stored once per body, then processed by a job (M5-P3, spec R13).

    Not tenant data: a webhook names no clinic. The payload is redacted before it is stored.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (
        Index(
            "ix_webhook_events_received_at_unprocessed",
            "received_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
        Index("ix_webhook_events_received_at", "received_at"),
    )

    provider: Mapped[str] = mapped_column(Text)
    event_key: Mapped[str] = mapped_column(Text, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(Text)
