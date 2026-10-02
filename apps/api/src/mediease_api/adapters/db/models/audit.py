"""The ``audit_events`` table (migration 0004, docs/DATA_MODEL.md "M1").

Append-only by construction: no ``updated_at``, no repository that updates it,
and two database triggers that refuse ``UPDATE``, ``DELETE`` and ``TRUNCATE``
(FR-AUD-02, AC6). ``clinic_id`` is nullable because platform-level actions
(sign-in, ops work) belong to a user, not a clinic.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, enum_check
from mediease_api.domain.audit.event import ActorType


class AuditEventRow(Keyed, Base):
    """One recorded action. Written only by ``adapters/db/audit.py``."""

    __tablename__ = "audit_events"
    __table_args__ = (
        enum_check("actor_type", ActorType),
        # "What happened in this clinic, newest first" and the same per actor.
        # Stored ascending: PostgreSQL scans a btree backwards, so these serve
        # ORDER BY occurred_at DESC without a DESC index.
        Index("ix_audit_events_clinic_id_occurred_at", "clinic_id", "occurred_at"),
        Index("ix_audit_events_actor_user_id_occurred_at", "actor_user_id", "occurred_at"),
    )

    clinic_id: Mapped[UUID | None] = mapped_column(ForeignKey("clinics.id"))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_type: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[UUID | None] = mapped_column()
    request_id: Mapped[str | None] = mapped_column(Text)
    # Salted HMAC of the caller's IP (ports/security.py::IpHasher), never the address.
    ip_hash: Mapped[str | None] = mapped_column(Text)
    # "metadata" is taken on a declarative class, so the attribute is renamed.
    event_metadata: Mapped[dict[str, str]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
