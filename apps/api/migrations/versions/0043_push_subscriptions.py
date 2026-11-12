"""web push subscriptions and the PUSH preference channel (M7e-E2)

Spec web-push §3, R10-R19; ADR-0025. Expand-only.

- ``push_subscriptions``: platform data owned by exactly one patient account or one staff user
  (a CHECK), never a clinic. The endpoint and keys are stored encrypted; ``endpoint_digest``
  (SHA-256 hex of the endpoint) is unique, so one browser is one row with one owner. Deleting
  the account or the user deletes its devices.
- ``notification_preferences.channel`` and ``patient_notification_preferences.channel`` allow
  ``PUSH``. Downgrade deletes the push preference rows first.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STAFF_BEFORE = "'IN_APP', 'WHATSAPP', 'EMAIL', 'SMS'"
_STAFF_AFTER = "'IN_APP', 'WHATSAPP', 'EMAIL', 'SMS', 'PUSH'"
_PATIENT_BEFORE = "'IN_APP', 'EMAIL'"
_PATIENT_AFTER = "'IN_APP', 'EMAIL', 'PUSH'"


def _channels(table: str, values: str) -> None:
    name = op.f(f"ck_{table}_channel")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, f"channel IN ({values})")


def upgrade() -> None:
    t = "push_subscriptions"
    op.create_table(
        t,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("endpoint_digest", sa.Text(), nullable=False),
        sa.Column("endpoint_encrypted", sa.Text(), nullable=False),
        sa.Column("p256dh_encrypted", sa.Text(), nullable=False),
        sa.Column("auth_encrypted", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(account_id IS NULL) <> (user_id IS NULL)", name=op.f(f"ck_{t}_one_owner")
        ),
        sa.CheckConstraint("disabled_reason IN ('EXPIRED')", name=op.f(f"ck_{t}_disabled_reason")),
        sa.CheckConstraint(
            "(disabled_at IS NULL) = (disabled_reason IS NULL)",
            name=op.f(f"ck_{t}_disabled_has_reason"),
        ),
        sa.CheckConstraint(
            "char_length(label) BETWEEN 1 AND 60", name=op.f(f"ck_{t}_label_length")
        ),
        sa.CheckConstraint(
            "endpoint_digest ~ '^[0-9a-f]{64}$'", name=op.f(f"ck_{t}_endpoint_digest_hex")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f(f"fk_{t}_account_id_patient_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f(f"fk_{t}_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("endpoint_digest", name=op.f(f"uq_{t}_endpoint_digest")),
    )
    op.create_index(op.f(f"ix_{t}_account_id"), t, ["account_id"])
    op.create_index(op.f(f"ix_{t}_user_id"), t, ["user_id"])
    _channels("notification_preferences", _STAFF_AFTER)
    _channels("patient_notification_preferences", _PATIENT_AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM notification_preferences WHERE channel = 'PUSH'")
    op.execute("DELETE FROM patient_notification_preferences WHERE channel = 'PUSH'")
    _channels("patient_notification_preferences", _PATIENT_BEFORE)
    _channels("notification_preferences", _STAFF_BEFORE)
    op.drop_table("push_subscriptions")
