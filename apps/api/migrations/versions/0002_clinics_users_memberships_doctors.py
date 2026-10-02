"""clinics, users, clinic memberships and doctors (M1-P1)

The first application tables (docs/DATA_MODEL.md "M1"). Written by hand to
match ``mediease_api.adapters.db.models``; ``test_models_match_migrations``
fails if the two drift. Enum values are the domain's at the time of writing
and are spelled out here on purpose: a migration must not change when the code
changes later.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "clinics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), server_default=sa.text("'Asia/Kolkata'"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=True),
        sa.Column("address_line", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("pincode", sa.Text(), nullable=True),
        sa.Column(
            "specialties",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('ONBOARDING', 'ACTIVE', 'SUSPENDED')", name=op.f("ck_clinics_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinics")),
        sa.UniqueConstraint("slug", name=op.f("uq_clinics_slug")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone_e164", sa.Text(), nullable=True),
        sa.Column("is_platform_ops", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name=op.f("ck_users_status")),
        sa.CheckConstraint(
            "email IS NOT NULL OR phone_e164 IS NOT NULL", name=op.f("ck_users_email_or_phone")
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lower_case")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("phone_e164", name=op.f("uq_users_phone_e164")),
    )

    op.create_table(
        "clinic_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "role IN ('OWNER', 'DOCTOR', 'FRONT_DESK')", name=op.f("ck_clinic_memberships_role")
        ),
        sa.CheckConstraint(
            "status IN ('INVITED', 'ACTIVE', 'DEACTIVATED')",
            name=op.f("ck_clinic_memberships_status"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_clinic_memberships_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_clinic_memberships_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinic_memberships")),
        sa.UniqueConstraint(
            "clinic_id", "user_id", name=op.f("uq_clinic_memberships_clinic_id_user_id")
        ),
    )
    op.create_index("ix_clinic_memberships_user_id", "clinic_memberships", ["user_id"])

    op.create_table(
        "doctors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("qualification", sa.Text(), nullable=False),
        sa.Column("registration_number", sa.Text(), nullable=False),
        sa.Column("registration_council", sa.Text(), nullable=False),
        sa.Column("specialty", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_doctors_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_doctors_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctors")),
    )
    op.create_index("ix_doctors_clinic_id", "doctors", ["clinic_id"])
    op.create_index(
        "uq_doctors_clinic_id_user_id",
        "doctors",
        ["clinic_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("doctors")
    op.drop_table("clinic_memberships")
    op.drop_table("users")
    op.drop_table("clinics")
