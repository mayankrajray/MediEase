"""message costs in millipaise and the monthly index (M5-P5)

Spec reminders-and-messaging R18; M5-P5 decisions 5A, 6A, 7A.

``messages.cost_paise`` (never written) becomes ``cost_millipaise``: Meta's Indian rates have four
rupee decimals (utility 11.5 paise), so money stays an integer one thousandth of a paisa finer.
``ck_messages_cost_not_negative`` guards it; ``ix_messages_clinic_id_sent_at`` serves the ops
monthly total per clinic.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("messages", "cost_paise", new_column_name="cost_millipaise")
    op.create_check_constraint(
        op.f("ck_messages_cost_not_negative"),
        "messages",
        "cost_millipaise IS NULL OR cost_millipaise >= 0",
    )
    op.create_index("ix_messages_clinic_id_sent_at", "messages", ["clinic_id", "sent_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_clinic_id_sent_at", table_name="messages")
    op.drop_constraint(op.f("ck_messages_cost_not_negative"), "messages", type_="check")
    # Whole paise, rounded half up, so a downgrade keeps the order of magnitude.
    op.execute("UPDATE messages SET cost_millipaise = (cost_millipaise + 500) / 1000")
    op.alter_column("messages", "cost_millipaise", new_column_name="cost_paise")
