"""clinic plans and trials (M6d-P7)

Spec plans-and-trial R1-R10; FR-SUB-01; decisions B9, D4, D5. Expand-only.

- ``clinic_subscriptions``: platform data, one row per clinic (keyed by it). The plan (``SOLO``,
  ``CLINIC``, ``PLUS``), whether a trial is owed, the 14-day trial once the clinic is active, and
  the last plan change by ops.
- Every existing clinic gets ``PLUS`` with no trial, so no current clinic meets a new limit (B9).

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    t = "clinic_subscriptions"
    op.create_table(
        t,
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("has_trial", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_changed_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("plan IN ('SOLO', 'CLINIC', 'PLUS')", name=op.f(f"ck_{t}_plan")),
        sa.CheckConstraint(
            "(trial_started_at IS NULL) = (trial_ends_at IS NULL)",
            name=op.f(f"ck_{t}_trial_together"),
        ),
        sa.CheckConstraint(
            "trial_ends_at IS NULL OR trial_ends_at = trial_started_at + interval '14 days'",
            name=op.f(f"ck_{t}_trial_14_days"),
        ),
        sa.CheckConstraint(
            "has_trial OR trial_started_at IS NULL", name=op.f(f"ck_{t}_trial_only_if_owed")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["plan_changed_by"], ["users.id"], name=op.f(f"fk_{t}_plan_changed_by_users")
        ),
        sa.PrimaryKeyConstraint("clinic_id", name=op.f(f"pk_{t}")),
    )
    # B9: existing clinics keep working as before, on the largest plan and owed no trial.
    op.execute(
        "INSERT INTO clinic_subscriptions (clinic_id, plan, has_trial, created_at, updated_at)"
        " SELECT id, 'PLUS', false, now(), now() FROM clinics"
    )


def downgrade() -> None:
    op.drop_table("clinic_subscriptions")
