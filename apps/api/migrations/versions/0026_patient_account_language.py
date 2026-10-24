"""the patient portal's language on the account (M6b-P2)

Patient portal spec R21; decision 2A. ``patient_accounts.language`` (``en`` or ``hi``, default
``en``), chosen by the person and kept across devices. Expand-only.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patient_accounts",
        sa.Column("language", sa.Text(), server_default=sa.text("'en'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_patient_accounts_language"), "patient_accounts", "language IN ('en', 'hi')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_patient_accounts_language"), "patient_accounts", type_="check")
    op.drop_column("patient_accounts", "language")
