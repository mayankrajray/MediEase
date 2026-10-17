"""favourites, templates and medicine-name history (M4-P3)

FR-RX-05, FR-RX-10; spec prescriptions R7; M4-P3 decisions 1A-5A; docs/DATA_MODEL.md "M4".
Expand-only.

``rx_favourites`` (one line) and ``rx_templates`` (a body) belong to one doctor; names are unique
per doctor ignoring case. ``prescription_items.favourite_id`` and ``prescriptions.template_id``
record where a line or body came from so issuing can count the use (3A); they are plain IDs, not
foreign keys, because issued rows never change and deleting a favourite must not touch them. The
P2 immutability trigger compares whole rows, so it covers the new columns without a change.

``ix_prescription_items_clinic_id_medicine_name`` serves start-of-name suggestions ignoring case,
the M2 pattern (5A): no extension.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _library(table: str, *body: sa.Column) -> None:
    op.create_table(
        table,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        *body,
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("use_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 100", name=op.f(f"ck_{table}_name_length")
        ),
        sa.CheckConstraint("revision >= 1", name=op.f(f"ck_{table}_revision_positive")),
        sa.CheckConstraint("use_count >= 0", name=op.f(f"ck_{table}_use_count_positive")),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{table}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f(f"fk_{table}_doctor_id_doctors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    )
    op.create_index(
        f"uq_{table}_doctor_id_name",
        table,
        ["doctor_id", sa.text("lower(name)")],
        unique=True,
    )


def upgrade() -> None:
    _library(
        "rx_favourites",
        sa.Column("item", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    _library(
        "rx_templates",
        sa.Column(
            "items",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "advice",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("follow_up_days", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_rx_templates_follow_up_days_range"),
        "rx_templates",
        "follow_up_days IS NULL OR follow_up_days BETWEEN 1 AND 365",
    )
    op.add_column("prescription_items", sa.Column("favourite_id", sa.Uuid(), nullable=True))
    op.add_column("prescriptions", sa.Column("template_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_prescription_items_clinic_id_medicine_name"),
        "prescription_items",
        ["clinic_id", sa.text("lower(medicine_name) text_pattern_ops")],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_prescription_items_clinic_id_medicine_name"), table_name="prescription_items"
    )
    # The items' trigger refuses changes to issued prescriptions' items; dropping a column is
    # DDL and is not seen by it.
    op.drop_column("prescriptions", "template_id")
    op.drop_column("prescription_items", "favourite_id")
    op.drop_table("rx_templates")
    op.drop_table("rx_favourites")
