"""in-app notifications and their preferences (M6a-P7)

ADR-0017; FR-NTF-03, 05, 06. ``notifications``: one row per staff member and event, unique on
``(clinic_id, recipient_user_id, event_key)`` so a replayed event adds nothing; titles come from a
typed, non-clinical catalogue. ``notification_preferences``: a member's choice per kind and
channel, a row only when changed from the default (on). Both are tenant data. Purged 90 days after
creation by the retention job. Expand-only.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = (
    "'appointment.booked', 'appointment.rescheduled', 'appointment.cancelled',"
    " 'appointment.arrived', 'message.failed', 'staff.joined'"
)


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"kind IN ({_KINDS})", name=op.f("ck_notifications_kind")),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_notifications_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_notifications_recipient_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "clinic_id",
            "recipient_user_id",
            "event_key",
            name=op.f("uq_notifications_clinic_id_recipient_user_id_event_key"),
        ),
    )
    op.create_index(
        "ix_notifications_clinic_id_recipient_user_id_created_at",
        "notifications",
        ["clinic_id", "recipient_user_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"kind IN ({_KINDS})", name=op.f("ck_notification_preferences_kind")),
        sa.CheckConstraint(
            "channel IN ('IN_APP', 'WHATSAPP', 'EMAIL', 'SMS')",
            name=op.f("ck_notification_preferences_channel"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name=op.f("fk_notification_preferences_clinic_id_clinics"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notification_preferences_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_preferences")),
        sa.UniqueConstraint(
            "clinic_id",
            "user_id",
            "kind",
            "channel",
            name=op.f("uq_notification_preferences_clinic_id_user_id_kind_channel"),
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index(
        "ix_notifications_clinic_id_recipient_user_id_created_at", table_name="notifications"
    )
    op.drop_table("notifications")
