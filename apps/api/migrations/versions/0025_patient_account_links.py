"""patient account links and portal invites (M6b-P1)

Patient portal spec R1-R9; decisions 1A-3A. Expand-only.

- ``patient_account_links``: a patient account linked to one clinic's patient record, made by an
  ``INVITE`` or an ``RX_LINK`` check. At most one active link per record and one per account in
  a clinic (partial unique indexes); revoked links stay as history with ``revoked_by``.
- ``patient_portal_invites``: single-use invites, stored as the SHA-256 digest of the secret,
  valid seven days; at most one pending (neither used nor superseded) per record.

Both are tenant data.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_account_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "method IN ('INVITE', 'RX_LINK')", name=op.f("ck_patient_account_links_method")
        ),
        sa.CheckConstraint(
            "revoked_by IN ('PATIENT', 'STAFF')", name=op.f("ck_patient_account_links_revoked_by")
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)",
            name=op.f("ck_patient_account_links_revoked_together"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_patient_account_links_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_patient_account_links_patient_id_patients"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f("fk_patient_account_links_account_id_patient_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_patient_account_links_created_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_account_links")),
    )
    op.create_index(
        "uq_patient_account_links_patient_active",
        "patient_account_links",
        ["clinic_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_patient_account_links_account_active",
        "patient_account_links",
        ["clinic_id", "account_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_patient_account_links_account_id_active",
        "patient_account_links",
        ["account_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "patient_portal_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_account_id", sa.Uuid(), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(used_at IS NULL) = (used_by_account_id IS NULL)",
            name=op.f("ck_patient_portal_invites_used_together"),
        ),
        sa.CheckConstraint(
            "used_at IS NULL OR superseded_at IS NULL",
            name=op.f("ck_patient_portal_invites_used_or_superseded"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_patient_portal_invites_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name=op.f("fk_patient_portal_invites_patient_id_patients"),
        ),
        sa.ForeignKeyConstraint(
            ["used_by_account_id"],
            ["patient_accounts.id"],
            name=op.f("fk_patient_portal_invites_used_by_account_id_patient_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_patient_portal_invites_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_portal_invites")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_patient_portal_invites_token_hash")),
    )
    op.create_index(
        "uq_patient_portal_invites_patient_pending",
        "patient_portal_invites",
        ["clinic_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text("used_at IS NULL AND superseded_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_patient_portal_invites_patient_pending", table_name="patient_portal_invites")
    op.drop_table("patient_portal_invites")
    op.drop_index("ix_patient_account_links_account_id_active", table_name="patient_account_links")
    op.drop_index("uq_patient_account_links_account_active", table_name="patient_account_links")
    op.drop_index("uq_patient_account_links_patient_active", table_name="patient_account_links")
    op.drop_table("patient_account_links")
