"""outbound messages and their health view (M5-P2)

FR-MSG-01, 02, 04; spec reminders-and-messaging R6-R8; docs/DATA_MODEL.md ``messages``.
Expand-only.

``messages``: one row per message, written before the provider is called. ``idempotency_key`` is
unique, so a job retried after a crash can never make a second row (R6, AC4);
``provider_message_id`` is unique for the status webhooks of P3. The phone number is Fernet
ciphertext (``to_phone_encrypted``) and ``variables`` hold no clinical text and no signed link.
``v_message_health`` is a support view with counts and ages by channel, template and status; it
holds no clinic or patient data.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("template_key", sa.Text(), nullable=False),
        sa.Column("template_version", sa.SmallInteger(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("to_phone_encrypted", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("cost_paise", sa.BigInteger(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("sending_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "channel IN ('WHATSAPP', 'SMS', 'CONSOLE')", name=op.f("ck_messages_channel")
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'SENT', 'DELIVERED', 'READ', 'FAILED')",
            name=op.f("ck_messages_status"),
        ),
        sa.CheckConstraint("language IN ('en', 'hi')", name=op.f("ck_messages_language")),
        sa.CheckConstraint(
            "source_type IN ('APPOINTMENT', 'PRESCRIPTION')", name=op.f("ck_messages_source_type")
        ),
        sa.CheckConstraint(
            "template_version >= 1", name=op.f("ck_messages_template_version_positive")
        ),
        sa.CheckConstraint(
            "(status IN ('SENT', 'DELIVERED', 'READ'))"
            " = (sent_at IS NOT NULL AND provider_message_id IS NOT NULL)",
            name=op.f("ck_messages_sent_has_provider_id"),
        ),
        sa.CheckConstraint(
            "(status = 'FAILED') = (failed_at IS NOT NULL AND error_code IS NOT NULL)",
            name=op.f("ck_messages_failed_has_code"),
        ),
        sa.CheckConstraint(
            "sending_started_at IS NULL OR status = 'QUEUED'",
            name=op.f("ck_messages_started_only_queued"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_messages_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f("fk_messages_patient_id_patients")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_messages_idempotency_key")),
        sa.UniqueConstraint("provider_message_id", name=op.f("uq_messages_provider_message_id")),
    )
    op.create_index("ix_messages_clinic_id_patient_id", "messages", ["clinic_id", "patient_id"])
    op.create_index(
        "ix_messages_clinic_id_source_type_source_id",
        "messages",
        ["clinic_id", "source_type", "source_id"],
    )
    op.execute(
        """
        CREATE VIEW v_message_health AS
        SELECT channel,
               template_key,
               status,
               count(*) AS total,
               count(*) FILTER (WHERE created_at > now() - interval '24 hours') AS last_24h,
               count(*) FILTER (WHERE error_code = 'MSG_OUTCOME_UNKNOWN') AS outcome_unknown,
               floor(extract(epoch FROM now() - min(created_at) FILTER (
                   WHERE status = 'QUEUED'
               )))::bigint AS oldest_queued_age_seconds
        FROM messages
        GROUP BY channel, template_key, status
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_message_health")
    op.drop_table("messages")
