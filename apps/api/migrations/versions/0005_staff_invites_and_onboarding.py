"""staff invitations on memberships and the onboarding checklist (M1-P5)

FR-ORG-04, FR-OPS-04; spec R12; docs/DATA_MODEL.md "M1". Expand-only: three
nullable columns and one new table, so M1-P4 code keeps working against it.

The invitation lives on ``clinic_memberships`` because an ``INVITED``
membership already *is* the pending invitation: one row, no second state to
reconcile, and invariant I2 keeps duplicates out. Only the SHA-256 digest of
the secret is stored (unique, so a digest cannot be shared), and the digest
survives acceptance so a replay can be told apart from an unknown secret.

``onboarding_checklists`` has one row per clinic and records the first time
each step happened (R12). The patient, appointment and prescription columns
exist from the start so the measurement for goal G4 is not retrofitted in
M2-M4.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clinic_memberships", sa.Column("invite_token_hash", sa.Text(), nullable=True))
    op.add_column(
        "clinic_memberships",
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "clinic_memberships",
        sa.Column("invite_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        op.f("uq_clinic_memberships_invite_token_hash"),
        "clinic_memberships",
        ["invite_token_hash"],
    )

    op.create_table(
        "onboarding_checklists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clinic_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doctors_added_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("patients_imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_appointment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_prescription_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name=op.f("fk_onboarding_checklists_clinic_id_clinics"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onboarding_checklists")),
        sa.UniqueConstraint("clinic_id", name=op.f("uq_onboarding_checklists_clinic_id")),
    )


def downgrade() -> None:
    op.drop_table("onboarding_checklists")
    op.drop_constraint(
        op.f("uq_clinic_memberships_invite_token_hash"), "clinic_memberships", type_="unique"
    )
    op.drop_column("clinic_memberships", "invite_accepted_at")
    op.drop_column("clinic_memberships", "invite_expires_at")
    op.drop_column("clinic_memberships", "invite_token_hash")
