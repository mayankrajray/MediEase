"""patient links, public rate limits and the prescription layout version (M4-P5)

FR-RX-07, 08; spec prescriptions R9-R13; M4-P5 decisions 1A-6A and the developer's layout
version addition; docs/DATA_MODEL.md "M4". Expand-only.

``patient_links``: one active link per prescription chain (partial unique index on
``prescription_id`` while not revoked); five failed challenges set ``locked_at`` (a CHECK keeps
the two in step). ``public_rate_limits``: one row per bucket and minute, shared by every API
worker; not tenant data. ``prescriptions.layout_version`` is the printed layout fixed at issue;
existing rows get 1, the only layout so far. Adding a column with a default is DDL, so the P2
immutability trigger is not involved, and it compares whole rows, so it now also keeps an issued
version's layout fixed.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prescriptions",
        sa.Column("layout_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_prescriptions_layout_version_positive"), "prescriptions", "layout_version >= 1"
    )

    op.create_table(
        "patient_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("prescription_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "failed_challenges", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose IN ('RX_VIEW')", name=op.f("ck_patient_links_purpose")),
        sa.CheckConstraint(
            "failed_challenges BETWEEN 0 AND 5",
            name=op.f("ck_patient_links_failed_challenges_range"),
        ),
        sa.CheckConstraint(
            "(locked_at IS NOT NULL) = (failed_challenges = 5)",
            name=op.f("ck_patient_links_locked_at_five"),
        ),
        sa.CheckConstraint("open_count >= 0", name=op.f("ck_patient_links_open_count_positive")),
        sa.CheckConstraint(
            "key_id ~ '^[A-Za-z0-9_-]{1,16}$'", name=op.f("ck_patient_links_key_id_format")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_patient_links_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f("fk_patient_links_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(
            ["prescription_id"],
            ["prescriptions.id"],
            name=op.f("fk_patient_links_prescription_id_prescriptions"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_patient_links_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_links")),
    )
    op.create_index(
        "uq_patient_links_prescription_id_active",
        "patient_links",
        ["prescription_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_patient_links_clinic_id_patient_id", "patient_links", ["clinic_id", "patient_id"]
    )

    op.create_table(
        "public_rate_limits",
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.CheckConstraint("hits >= 1", name=op.f("ck_public_rate_limits_hits_positive")),
        sa.PrimaryKeyConstraint("bucket", "window_start", name=op.f("pk_public_rate_limits")),
    )
    op.create_index("ix_public_rate_limits_window_start", "public_rate_limits", ["window_start"])


def downgrade() -> None:
    op.drop_table("public_rate_limits")
    op.drop_table("patient_links")
    op.drop_constraint(
        op.f("ck_prescriptions_layout_version_positive"), "prescriptions", type_="check"
    )
    op.drop_column("prescriptions", "layout_version")
