"""payments and refunds on bills (M6d-P3)

Spec billing R31-R42; FR-BIL-03, FR-BIL-05; decision B6. Expand-only.

- ``payments``: a payment or refund on one bill, its mode (cash, UPI, card), amount in paise and
  an optional reference, who took it and the clinic-local day (the collection's day, P5). A void
  records its time, author and reason together. The bill's ``paid_paise`` and
  ``refunded_paise`` (0037) are kept in step by the application under the bill row lock.

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    t = "payments"
    op.create_table(
        t,
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("received_by", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.Uuid(), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("kind IN ('PAYMENT', 'REFUND')", name=op.f(f"ck_{t}_kind")),
        sa.CheckConstraint("mode IN ('CASH', 'UPI', 'CARD')", name=op.f(f"ck_{t}_mode")),
        sa.CheckConstraint(
            "(voided_at IS NULL) = (voided_by IS NULL)"
            " AND (voided_at IS NULL) = (void_reason IS NULL)",
            name=op.f(f"ck_{t}_voided_together"),
        ),
        sa.CheckConstraint(
            "amount_paise BETWEEN 1 AND 100000000", name=op.f(f"ck_{t}_amount_range")
        ),
        sa.CheckConstraint(
            "reference IS NULL OR char_length(reference) <= 40",
            name=op.f(f"ck_{t}_reference_length"),
        ),
        sa.CheckConstraint(
            "void_reason IS NULL OR char_length(void_reason) <= 200",
            name=op.f(f"ck_{t}_void_reason_length"),
        ),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], name=op.f(f"fk_{t}_bill_id_bills")),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f(f"fk_{t}_doctor_id_doctors")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f(f"fk_{t}_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(
            ["received_by"], ["users.id"], name=op.f(f"fk_{t}_received_by_users")
        ),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], name=op.f(f"fk_{t}_voided_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index("ix_payments_bill_id", t, ["bill_id"])
    op.create_index("ix_payments_clinic_id_local_date", t, ["clinic_id", "local_date"])


def downgrade() -> None:
    op.drop_table("payments")
