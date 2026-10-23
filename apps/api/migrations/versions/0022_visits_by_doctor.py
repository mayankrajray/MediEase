"""an index for the patients a doctor has seen (M6a-P6)

FR-UX-02, FR-UX-06 (decision 5A). ``GET /my-patients`` groups one doctor's visits by patient;
``ix_visits_clinic_id_doctor_id_started_at`` serves it. Expand-only, no data change.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_visits_clinic_id_doctor_id_started_at",
        "visits",
        ["clinic_id", "doctor_id", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_visits_clinic_id_doctor_id_started_at", table_name="visits")
