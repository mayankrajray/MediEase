"""reports attached to visits (M6d-P6)

Spec visit-attachments R1-R14; FR-VIS-04; decisions B8, D7. Expand-only.

- ``visit_attachments``: a PDF, JPEG or PNG of at most 10 MB on a visit, kept in blob storage
  under ``storage_key`` (``attachments/{clinic}/{visit}/{id}``). Who attached it and when; when
  and by whom it was shared with the patient's portal; and a delete (within 24 hours, by the
  uploader) as its time and author, the row kept. The file name is clinical: never logged.

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    t = "visit_attachments"
    op.create_table(
        t,
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shared_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Uuid(), nullable=True),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name=op.f(f"ck_{t}_content_type"),
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 10485760", name=op.f(f"ck_{t}_size_bytes_range")
        ),
        sa.CheckConstraint(
            "char_length(filename) BETWEEN 1 AND 120", name=op.f(f"ck_{t}_filename_length")
        ),
        sa.CheckConstraint(
            "(shared_at IS NULL) = (shared_by IS NULL)", name=op.f(f"ck_{t}_shared_together")
        ),
        sa.CheckConstraint(
            "(deleted_at IS NULL) = (deleted_by IS NULL)", name=op.f(f"ck_{t}_deleted_together")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"], ["users.id"], name=op.f(f"fk_{t}_deleted_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f(f"fk_{t}_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(["shared_by"], ["users.id"], name=op.f(f"fk_{t}_shared_by_users")),
        sa.ForeignKeyConstraint(
            ["uploaded_by"], ["users.id"], name=op.f(f"fk_{t}_uploaded_by_users")
        ),
        sa.ForeignKeyConstraint(["visit_id"], ["visits.id"], name=op.f(f"fk_{t}_visit_id_visits")),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("storage_key", name=op.f(f"uq_{t}_storage_key")),
    )
    op.create_index("ix_visit_attachments_visit_id_uploaded_at", t, ["visit_id", "uploaded_at"])
    op.create_index(
        "ix_visit_attachments_clinic_id_patient_id_shared_at",
        t,
        ["clinic_id", "patient_id", "shared_at"],
        postgresql_where=sa.text("shared_at IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("visit_attachments")
