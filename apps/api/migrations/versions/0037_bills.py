"""bills and credit notes (M6d-P2)

Spec billing R13-R30; FR-BIL-02, FR-BIL-07; ADR-0022. Expand-only.

- ``bills``: a bill or a credit note (``kind``), a snapshot of its lines (B3); ``DRAFT`` without a
  number, ``ISSUED`` numbered per clinic, kind and financial year (B5), ``CANCELLED`` once fully
  credited. ``credited_paise``, ``paid_paise`` and ``refunded_paise`` are kept on the bill (the
  latter two from P3). One open bill per visit.
- ``bill_lines``: each line's price, quantity, discounts and final amount (a CHECK ties them);
  a credit note's line names the bill line it reverses, at most once (a unique index).

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOTAL = "BETWEEN 0 AND 100000000"


def upgrade() -> None:
    b = "bills"
    op.create_table(
        b,
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=True),
        sa.Column("doctor_id", sa.Uuid(), nullable=True),
        sa.Column("discount_kind", sa.Text(), nullable=False),
        sa.Column("discount_value", sa.Integer(), nullable=False),
        sa.Column("subtotal_paise", sa.Integer(), nullable=False),
        sa.Column("discount_paise", sa.Integer(), nullable=False),
        sa.Column("total_paise", sa.Integer(), nullable=False),
        sa.Column("credited_paise", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("paid_paise", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("refunded_paise", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("number", sa.Text(), nullable=True),
        sa.Column("financial_year", sa.Text(), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=True),
        sa.Column("bill_date", sa.Date(), nullable=True),
        sa.Column("credits_bill_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("issued_by", sa.Uuid(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(kind = 'CREDIT_NOTE') = (credits_bill_id IS NOT NULL)"
            " AND (kind = 'BILL' OR (status = 'ISSUED' AND reason IS NOT NULL))",
            name=op.f(f"ck_{b}_credit_note_shape"),
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT') = (number IS NULL)"
            " AND (number IS NULL) = (seq IS NULL)"
            " AND (number IS NULL) = (financial_year IS NULL)"
            " AND (number IS NULL) = (bill_date IS NULL)"
            " AND (number IS NULL) = (issued_at IS NULL)",
            name=op.f(f"ck_{b}_numbered_when_issued"),
        ),
        sa.CheckConstraint(
            "discount_kind IN ('NONE', 'AMOUNT', 'PERCENT')", name=op.f(f"ck_{b}_discount_kind")
        ),
        sa.CheckConstraint("kind IN ('BILL', 'CREDIT_NOTE')", name=op.f(f"ck_{b}_kind")),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'CANCELLED')", name=op.f(f"ck_{b}_status")
        ),
        sa.CheckConstraint(
            "credited_paise BETWEEN 0 AND total_paise AND paid_paise >= 0 AND refunded_paise >= 0",
            name=op.f(f"ck_{b}_money_range"),
        ),
        sa.CheckConstraint(
            "discount_paise BETWEEN 0 AND subtotal_paise", name=op.f(f"ck_{b}_discount_range")
        ),
        sa.CheckConstraint("discount_value >= 0", name=op.f(f"ck_{b}_discount_value_range")),
        sa.CheckConstraint(
            "notes IS NULL OR char_length(notes) <= 500", name=op.f(f"ck_{b}_notes_length")
        ),
        sa.CheckConstraint(
            "reason IS NULL OR char_length(reason) <= 200", name=op.f(f"ck_{b}_reason_length")
        ),
        sa.CheckConstraint(f"subtotal_paise {_TOTAL}", name=op.f(f"ck_{b}_subtotal_range")),
        sa.CheckConstraint(f"total_paise {_TOTAL}", name=op.f(f"ck_{b}_total_range")),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{b}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f(f"fk_{b}_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["credits_bill_id"], ["bills.id"], name=op.f(f"fk_{b}_credits_bill_id_bills")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f(f"fk_{b}_doctor_id_doctors")
        ),
        sa.ForeignKeyConstraint(["issued_by"], ["users.id"], name=op.f(f"fk_{b}_issued_by_users")),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f(f"fk_{b}_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(["visit_id"], ["visits.id"], name=op.f(f"fk_{b}_visit_id_visits")),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{b}")),
    )
    op.create_index("ix_bills_clinic_id_created_at", b, ["clinic_id", "created_at"])
    op.create_index("ix_bills_clinic_id_patient_id", b, ["clinic_id", "patient_id"])
    op.create_index("ix_bills_credits_bill_id", b, ["credits_bill_id"])
    op.create_index(
        "uq_bills_clinic_id_kind_financial_year_seq",
        b,
        ["clinic_id", "kind", "financial_year", "seq"],
        unique=True,
    )
    op.create_index(
        "uq_bills_visit_id",
        b,
        ["visit_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'BILL' AND status <> 'CANCELLED'"),
    )

    li = "bill_lines"
    op.create_table(
        li,
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit_price_paise", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("discount_kind", sa.Text(), nullable=False),
        sa.Column("discount_value", sa.Integer(), nullable=False),
        sa.Column("discount_paise", sa.Integer(), nullable=False),
        sa.Column("bill_discount_paise", sa.Integer(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("credits_line_id", sa.Uuid(), nullable=True),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "discount_kind IN ('NONE', 'AMOUNT', 'PERCENT')", name=op.f(f"ck_{li}_discount_kind")
        ),
        sa.CheckConstraint(
            "char_length(description) BETWEEN 1 AND 80", name=op.f(f"ck_{li}_description_length")
        ),
        sa.CheckConstraint(
            "discount_value >= 0 AND discount_paise >= 0 AND bill_discount_paise >= 0"
            " AND amount_paise >= 0"
            " AND amount_paise"
            " = unit_price_paise * quantity - discount_paise - bill_discount_paise",
            name=op.f(f"ck_{li}_amounts"),
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 50", name=op.f(f"ck_{li}_position_range")),
        sa.CheckConstraint("quantity BETWEEN 1 AND 99", name=op.f(f"ck_{li}_quantity_range")),
        sa.CheckConstraint(
            "unit_price_paise BETWEEN 0 AND 10000000", name=op.f(f"ck_{li}_unit_price_range")
        ),
        sa.ForeignKeyConstraint(
            ["bill_id"], ["bills.id"], name=op.f(f"fk_{li}_bill_id_bills"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{li}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["credits_line_id"],
            ["bill_lines.id"],
            name=op.f(f"fk_{li}_credits_line_id_bill_lines"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["clinic_services.id"],
            name=op.f(f"fk_{li}_service_id_clinic_services"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{li}")),
    )
    op.create_index("uq_bill_lines_bill_id_position", li, ["bill_id", "position"], unique=True)
    op.create_index("uq_bill_lines_credits_line_id", li, ["credits_line_id"], unique=True)


def downgrade() -> None:
    op.drop_table("bill_lines")
    op.drop_table("bills")
