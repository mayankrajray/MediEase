"""baseline

The empty starting point of the schema history (M0-P3). It creates no tables;
applying it only records revision 0001 in ``alembic_version``. The first tables
arrive in M1 as revision 0002.

Revision ID: 0001
Revises:
Create Date: 2026-10-02
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
