"""opt-out by replying STOP (M5-P5)

FR-MSG-05; spec reminders-and-messaging R14, AC5; M5-P5 decisions 2A, 3A. Expand-only.

``ix_patients_phone_e164``: a STOP reply names a number, not a clinic, so the reviewed opt-out
lookup matches patients by number alone. ``messages.source_type`` gains ``OPT_OUT`` (the reply
that confirms a STOP). The new job kind ``send_opt_out_confirmation`` belongs to a clinic, so
``ck_jobs_system_kind`` is unchanged.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _source_types(values: str) -> None:
    op.drop_constraint(op.f("ck_messages_source_type"), "messages", type_="check")
    op.create_check_constraint(
        op.f("ck_messages_source_type"), "messages", f"source_type IN ({values})"
    )


def upgrade() -> None:
    op.create_index("ix_patients_phone_e164", "patients", ["phone_e164"])
    _source_types("'APPOINTMENT', 'PRESCRIPTION', 'REMINDER', 'OPT_OUT'")


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE kind = 'send_opt_out_confirmation'")
    op.execute("DELETE FROM messages WHERE source_type = 'OPT_OUT'")
    _source_types("'APPOINTMENT', 'PRESCRIPTION', 'REMINDER'")
    op.drop_index("ix_patients_phone_e164", table_name="patients")
