"""patient notifications, their preferences and the medicine-due sweep (M6b-P6)

Portal spec R55-R66, R73; developer approval 26 Oct 2026. Expand-only.

- ``patient_notifications`` (tenant): one row per notification for one account; no text, only
  ``params`` (IDs, a time, a token, a slot, a reason code). ``(account_id, event_key)`` is unique,
  so a replayed or concurrent event inserts nothing (R58).
- ``patient_notification_preferences`` (the account's, no clinic): per kind and channel.
- ``ck_jobs_system_kind``: ``schedule_medicine_due`` (the 5-minute sweep).

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = (
    "'booking.accepted', 'booking.declined', 'booking.proposed', 'booking.expired',"
    " 'appointment.confirmed', 'appointment.moved', 'appointment.cancelled',"
    " 'prescription.ready', 'medicine.due'"
)
_OLD_SYSTEM = (
    "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages',"
    " 'schedule_no_shows', 'schedule_request_expiry', 'send_auth_email'"
)
_NEW_SYSTEM = (
    "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages',"
    " 'schedule_medicine_due', 'schedule_no_shows', 'schedule_request_expiry', 'send_auth_email'"
)


def _system_kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_jobs_system_kind"), "jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_jobs_system_kind"), "jobs", f"(clinic_id IS NULL) = (kind IN ({kinds}))"
    )


def upgrade() -> None:
    t = "patient_notifications"
    op.create_table(
        t,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"kind IN ({_KINDS})", name=op.f(f"ck_{t}_kind")),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f(f"fk_{t}_account_id_patient_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("account_id", "event_key", name=op.f(f"uq_{t}_account_id_event_key")),
    )
    op.create_index(
        "ix_patient_notifications_account_id_created_at",
        t,
        ["account_id", sa.text("created_at DESC")],
    )
    op.create_index(op.f(f"ix_{t}_created_at"), t, ["created_at"])

    p = "patient_notification_preferences"
    op.create_table(
        p,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"kind IN ({_KINDS})", name=op.f(f"ck_{p}_kind")),
        sa.CheckConstraint("channel IN ('IN_APP', 'EMAIL')", name=op.f(f"ck_{p}_channel")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f(f"fk_{p}_account_id_patient_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{p}")),
        sa.UniqueConstraint(
            "account_id", "kind", "channel", name=op.f(f"uq_{p}_account_id_kind_channel")
        ),
    )
    _system_kinds(_NEW_SYSTEM)


def downgrade() -> None:
    op.execute(
        "DELETE FROM jobs WHERE kind IN"
        " ('schedule_medicine_due', 'notify_medicine_due', 'send_patient_email')"
    )
    _system_kinds(_OLD_SYSTEM)
    op.drop_table("patient_notification_preferences")
    op.drop_index("ix_patient_notifications_created_at", table_name="patient_notifications")
    op.drop_index(
        "ix_patient_notifications_account_id_created_at", table_name="patient_notifications"
    )
    op.drop_table("patient_notifications")
