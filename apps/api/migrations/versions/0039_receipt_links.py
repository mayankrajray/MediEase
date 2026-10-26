"""receipt links: a patient link to a bill (M6d-P4)

Spec billing R48-R51; FR-BIL-04; decision B7. Expand-only for prescriptions: their links keep
``prescription_id`` and behave as before.

- ``patient_links.bill_id`` (FK bills, null) for the new purpose ``RECEIPT``; ``prescription_id``
  becomes nullable, and a CHECK ties each purpose to its own column.
- One active receipt link per bill (partial unique index, like the prescription chain's).

Receipt PDFs need no column: each state of a bill has its own storage key.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

T = "patient_links"


def upgrade() -> None:
    op.add_column(T, sa.Column("bill_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f(f"fk_{T}_bill_id_bills"), T, "bills", ["bill_id"], ["id"])
    op.alter_column(T, "prescription_id", existing_type=sa.Uuid(), nullable=True)
    op.drop_constraint(op.f(f"ck_{T}_purpose"), T, type_="check")
    op.create_check_constraint(op.f(f"ck_{T}_purpose"), T, "purpose IN ('RX_VIEW', 'RECEIPT')")
    op.create_check_constraint(
        op.f(f"ck_{T}_resource_of_purpose"),
        T,
        "(purpose = 'RX_VIEW') = (prescription_id IS NOT NULL)"
        " AND (purpose = 'RECEIPT') = (bill_id IS NOT NULL)",
    )
    op.create_index(
        "uq_patient_links_bill_id_active",
        T,
        ["bill_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM patient_links WHERE purpose = 'RECEIPT'")
    op.drop_index("uq_patient_links_bill_id_active", table_name=T)
    op.drop_constraint(op.f(f"ck_{T}_resource_of_purpose"), T, type_="check")
    op.drop_constraint(op.f(f"ck_{T}_purpose"), T, type_="check")
    op.create_check_constraint(op.f(f"ck_{T}_purpose"), T, "purpose IN ('RX_VIEW')")
    op.alter_column(T, "prescription_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint(op.f(f"fk_{T}_bill_id_bills"), T, type_="foreignkey")
    op.drop_column(T, "bill_id")
