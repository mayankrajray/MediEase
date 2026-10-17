"""the clinic's prescription paper size (M4-P4)

FR-RX-04; spec prescriptions R8; M4-P4 decision 3A; docs/DATA_MODEL.md "M4". Expand-only.

``clinics.rx_paper_size`` is A5 (the default, also for existing clinics) or A4. It is read when a
prescription version is first rendered and then fixed in that version's stored PDF, whose key the
P2 trigger already lets ``prescriptions.pdf_object_key`` take once; no other table changes.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clinics",
        sa.Column("rx_paper_size", sa.Text(), server_default=sa.text("'A5'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_clinics_rx_paper_size"), "clinics", "rx_paper_size IN ('A5', 'A4')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_clinics_rx_paper_size"), "clinics", type_="check")
    op.drop_column("clinics", "rx_paper_size")
