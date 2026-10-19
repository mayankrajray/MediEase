"""follow-up reminders and the no-show sweep (M5-P4)

FR-REM-01, 02, 04, 05, 07; spec reminders-and-messaging R1-R5, R17; appointments R10;
M5-P4 decisions 1A, 3A, 4A. Expand-only.

``reminders``: one row per follow-up reminder, tenant-scoped. A prescription's reminder names its
chain (version 1) in ``source_id``; ``uq_reminders_source_id_scheduled`` keeps one ``SCHEDULED``
reminder per chain. ``revision`` counts moves, so a job made before a move does nothing.
``messages.source_type`` gains ``REMINDER``; ``ck_jobs_system_kind`` gains ``schedule_no_shows``.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_KINDS = "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages'"
_NEW_KINDS = (
    "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages',"
    " 'schedule_no_shows'"
)


def _system_kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_jobs_system_kind"), "jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_jobs_system_kind"), "jobs", f"(clinic_id IS NULL) = (kind IN ({kinds}))"
    )


def _source_types(values: str) -> None:
    op.drop_constraint(op.f("ck_messages_source_type"), "messages", type_="check")
    op.create_check_constraint(
        op.f("ck_messages_source_type"), "messages", f"source_type IN ({values})"
    )


def upgrade() -> None:
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("follow_up_date", sa.Date(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.SmallInteger(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('FOLLOW_UP')", name=op.f("ck_reminders_kind")),
        sa.CheckConstraint(
            "source IN ('PRESCRIPTION', 'MANUAL')", name=op.f("ck_reminders_source")
        ),
        sa.CheckConstraint(
            "status IN ('SCHEDULED', 'SENT', 'CANCELLED', 'SKIPPED_NO_CONSENT', 'FAILED')",
            name=op.f("ck_reminders_status"),
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_reminders_revision_positive")),
        sa.CheckConstraint(
            "(source = 'PRESCRIPTION') = (source_id IS NOT NULL)",
            name=op.f("ck_reminders_source_id"),
        ),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
            name=op.f("ck_reminders_cancelled_has_time"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_reminders_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f("fk_reminders_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f("fk_reminders_doctor_id_doctors")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["prescriptions.id"], name=op.f("fk_reminders_source_id_prescriptions")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_reminders_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"], ["users.id"], name=op.f("fk_reminders_cancelled_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
    )
    op.create_index(
        "uq_reminders_source_id_scheduled",
        "reminders",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status = 'SCHEDULED'"),
    )
    op.create_index("ix_reminders_clinic_id_patient_id", "reminders", ["clinic_id", "patient_id"])
    _source_types("'APPOINTMENT', 'PRESCRIPTION', 'REMINDER'")
    _system_kinds(_NEW_KINDS)


def downgrade() -> None:
    op.execute(
        "DELETE FROM jobs WHERE kind IN ('schedule_no_shows', 'mark_no_shows', 'send_reminder')"
    )
    _system_kinds(_OLD_KINDS)
    op.execute("DELETE FROM messages WHERE source_type = 'REMINDER'")
    _source_types("'APPOINTMENT', 'PRESCRIPTION'")
    op.drop_table("reminders")
