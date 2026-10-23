"""email verification and password-reset tokens (M6a-P4)

ADR-0016; FR-AUTH-08, FR-AUTH-05. ``email_tokens`` holds single-use tokens as SHA-256 digests,
each for exactly one staff user or patient account and the address it was sent to. Platform data,
not tenant data. ``ck_jobs_system_kind`` gains ``send_auth_email``: an account's email belongs to
no clinic. Expand-only.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_KINDS = (
    "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages',"
    " 'schedule_no_shows'"
)
_NEW_KINDS = (
    "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages',"
    " 'schedule_no_shows', 'send_auth_email'"
)


def _system_kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_jobs_system_kind"), "jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_jobs_system_kind"), "jobs", f"(clinic_id IS NULL) = (kind IN ({kinds}))"
    )


def upgrade() -> None:
    op.create_table(
        "email_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("patient_account_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('VERIFY_EMAIL', 'RESET_PASSWORD')", name=op.f("ck_email_tokens_purpose")
        ),
        sa.CheckConstraint(
            "(user_id IS NULL) <> (patient_account_id IS NULL)",
            name=op.f("ck_email_tokens_exactly_one_owner"),
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_email_tokens_email_lower_case")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_email_tokens_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["patient_account_id"],
            ["patient_accounts.id"],
            name=op.f("fk_email_tokens_patient_account_id_patient_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_tokens_token_hash")),
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])
    op.create_index("ix_email_tokens_patient_account_id", "email_tokens", ["patient_account_id"])
    op.create_index("ix_email_tokens_expires_at", "email_tokens", ["expires_at"])
    _system_kinds(_NEW_KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE kind = 'send_auth_email'")
    _system_kinds(_OLD_KINDS)
    op.drop_table("email_tokens")
