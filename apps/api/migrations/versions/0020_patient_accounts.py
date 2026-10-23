"""patient accounts, portal sessions and Google identities (M6a-P3)

ADR-0015; FR-AUTH-07, FR-PRT-01. Three platform tables, apart from ``users`` and
``refresh_tokens`` on purpose (decision 1), none of them tenant data:

- ``patient_accounts``: a password or a Google account. One password account per email
  (``uq_patient_accounts_password_email``, partial); a Google account may share its email with a
  password account and is never merged with it. ``email_verified_at`` is null until proved.
- ``patient_refresh_tokens``: portal session families, the ``refresh_tokens`` lifecycle.
- ``external_identities``: a provider ``sub`` linked to exactly one staff user or patient
  account, at most one of each kind per subject.

``audit_events.actor_type`` gains ``PATIENT``. Expand-only: nothing existing changes shape.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTOR_TYPES_BEFORE = "'STAFF', 'OPS', 'PATIENT_LINK', 'SYSTEM'"
_ACTOR_TYPES_AFTER = "'STAFF', 'OPS', 'PATIENT_LINK', 'SYSTEM', 'PATIENT'"


def upgrade() -> None:
    op.create_table(
        "patient_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sign_in_method", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sign_in_method IN ('PASSWORD', 'GOOGLE')",
            name=op.f("ck_patient_accounts_sign_in_method"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')", name=op.f("ck_patient_accounts_status")
        ),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_patient_accounts_email_lower_case")
        ),
        sa.CheckConstraint(
            "failed_login_count >= 0",
            name=op.f("ck_patient_accounts_failed_login_count_non_negative"),
        ),
        sa.CheckConstraint(
            "(sign_in_method = 'PASSWORD') = (password_hash IS NOT NULL)",
            name=op.f("ck_patient_accounts_password_matches_method"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_accounts")),
    )
    op.create_index(
        "uq_patient_accounts_password_email",
        "patient_accounts",
        ["email"],
        unique=True,
        postgresql_where=sa.text("sign_in_method = 'PASSWORD'"),
    )

    op.create_table(
        "patient_refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f("fk_patient_refresh_tokens_account_id_patient_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["patient_refresh_tokens.id"],
            name=op.f("fk_patient_refresh_tokens_replaced_by_id_patient_refresh_tokens"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_patient_refresh_tokens_token_hash")),
    )
    op.create_index("ix_patient_refresh_tokens_family_id", "patient_refresh_tokens", ["family_id"])
    op.create_index(
        "ix_patient_refresh_tokens_account_id", "patient_refresh_tokens", ["account_id"]
    )

    op.create_table(
        "external_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("patient_account_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("provider IN ('GOOGLE')", name=op.f("ck_external_identities_provider")),
        sa.CheckConstraint(
            "(user_id IS NULL) <> (patient_account_id IS NULL)",
            name=op.f("ck_external_identities_exactly_one_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_external_identities_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["patient_account_id"],
            ["patient_accounts.id"],
            name=op.f("fk_external_identities_patient_account_id_patient_accounts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_identities")),
    )
    op.create_index(
        "uq_external_identities_staff_subject",
        "external_identities",
        ["provider", "subject"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_external_identities_patient_subject",
        "external_identities",
        ["provider", "subject"],
        unique=True,
        postgresql_where=sa.text("patient_account_id IS NOT NULL"),
    )
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])
    op.create_index(
        "ix_external_identities_patient_account_id", "external_identities", ["patient_account_id"]
    )

    op.drop_constraint(op.f("ck_audit_events_actor_type"), "audit_events", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_events_actor_type"),
        "audit_events",
        f"actor_type IN ({_ACTOR_TYPES_AFTER})",
    )


def downgrade() -> None:
    # Refused while patient audit rows exist: audit_events is append-only (FR-AUD-02).
    op.drop_constraint(op.f("ck_audit_events_actor_type"), "audit_events", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_events_actor_type"),
        "audit_events",
        f"actor_type IN ({_ACTOR_TYPES_BEFORE})",
    )
    op.drop_table("external_identities")
    op.drop_table("patient_refresh_tokens")
    op.drop_table("patient_accounts")
