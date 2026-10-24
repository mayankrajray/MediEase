"""dose records: the patient's own Taken / Skipped marks (M6b-P3b)

Patient portal spec R45-R54; developer decisions D4, D5. Health data (C3), tenant rows reached
only from patient routes. One row per account, version, line, day and slot; a dose with no row is
"Not recorded" (never stored). ``keep_until`` is the day the purge may delete it: one year after
the course ends, or after the dose date for open-ended courses (subject to privacy and legal
review). ``item_id`` has no foreign key, as for reminder choices (0027). Expand-only.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_T = "dose_records"


def upgrade() -> None:
    t = _T
    op.create_table(
        t,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("prescription_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("keep_until", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "slot IN ('MORNING', 'AFTERNOON', 'EVENING', 'NIGHT')", name=op.f(f"ck_{t}_slot")
        ),
        sa.CheckConstraint("state IN ('TAKEN', 'SKIPPED')", name=op.f(f"ck_{t}_state")),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f(f"fk_{t}_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f(f"fk_{t}_account_id_patient_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["prescription_id"],
            ["prescriptions.id"],
            name=op.f(f"fk_{t}_prescription_id_prescriptions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint(
            "account_id",
            "prescription_id",
            "item_id",
            "on_date",
            "slot",
            name=op.f(f"uq_{t}_dose"),
        ),
    )
    op.create_index(
        op.f(f"ix_{t}_account_id_prescription_id"), t, ["account_id", "prescription_id"]
    )
    op.create_index(op.f(f"ix_{t}_keep_until"), t, ["keep_until"])


def downgrade() -> None:
    op.drop_index(op.f(f"ix_{_T}_keep_until"), table_name=_T)
    op.drop_index(op.f(f"ix_{_T}_account_id_prescription_id"), table_name=_T)
    op.drop_table(_T)
