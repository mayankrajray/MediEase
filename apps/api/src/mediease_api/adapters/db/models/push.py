"""Web push subscriptions (M7e-E2, migration 0043, docs/DATA_MODEL.md "M7e — Web push").

Platform data owned by exactly one patient account or one staff user, never a clinic: there is no
``clinic_id``, so no clinic read can reach it. The endpoint and keys are stored only encrypted;
``endpoint_digest`` (SHA-256 of the endpoint) finds a device again when its browser resubscribes.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, Timestamps, enum_check
from mediease_api.domain.push.subscription import LABEL_MAX, DisabledReason


class PushSubscriptionRow(Keyed, Timestamps, Base):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint_digest"),
        Index("ix_push_subscriptions_account_id", "account_id"),
        Index("ix_push_subscriptions_user_id", "user_id"),
        CheckConstraint("(account_id IS NULL) <> (user_id IS NULL)", name="one_owner"),
        enum_check("disabled_reason", DisabledReason),
        CheckConstraint(
            "(disabled_at IS NULL) = (disabled_reason IS NULL)", name="disabled_has_reason"
        ),
        CheckConstraint(f"char_length(label) BETWEEN 1 AND {LABEL_MAX}", name="label_length"),
        CheckConstraint("endpoint_digest ~ '^[0-9a-f]{64}$'", name="endpoint_digest_hex"),
    )

    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("patient_accounts.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint_digest: Mapped[str] = mapped_column(Text)
    endpoint_encrypted: Mapped[str] = mapped_column(Text)
    p256dh_encrypted: Mapped[str] = mapped_column(Text)
    auth_encrypted: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_reason: Mapped[str | None] = mapped_column(Text)
