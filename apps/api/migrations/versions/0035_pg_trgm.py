"""the pg_trgm extension for directory search (M6c-P6)

Spec discovery R1-R6; ADR-0021. Expand-only: ``CREATE EXTENSION IF NOT EXISTS pg_trgm`` (a
trusted extension since PostgreSQL 13, so the database owner may create it). No index yet: at
pilot scale the search reads a few hundred listed clinics; trigram indexes join with the read
model when the directory grows (ADR-0021).

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
