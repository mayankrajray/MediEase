"""visits and visit addenda (M4-P1)

FR-VIS-01, 02, 03, 05; spec prescriptions R1-R3; M4-P1 decisions 1A-6A; docs/DATA_MODEL.md "M4".
Expand-only.

``visits`` is the clinical record of one appointment (``appointment_id`` unique and not null:
walk-ins come through the queue first, decision 5A). The 24-hour lock is decided by the
application with its clock (decision 6A); the CHECK only keeps ``locked_at`` consistent with
``completed_at``. ``visit_addenda`` is append-only, enforced by triggers as ``audit_events`` is
(migration 0004): ``UPDATE``, ``DELETE`` and ``TRUNCATE`` raise ``VIS_ADDENDUM_APPEND_ONLY`` for
every non-superuser role, ours included.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TEXT_LIMITS = {"chief_complaint": 500, "findings": 5000, "diagnosis": 1000, "notes": 5000}

_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION visit_addenda_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'VIS_ADDENDUM_APPEND_ONLY: visit_addenda is append-only (FR-VIS-05); % is not allowed',
        TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$
"""

_APPEND_ONLY_TRIGGERS = (
    """
    CREATE TRIGGER trg_visit_addenda_no_update_delete
    BEFORE UPDATE OR DELETE ON visit_addenda
    FOR EACH ROW EXECUTE FUNCTION visit_addenda_append_only()
    """,
    """
    CREATE TRIGGER trg_visit_addenda_no_truncate
    BEFORE TRUNCATE ON visit_addenda
    FOR EACH STATEMENT EXECUTE FUNCTION visit_addenda_append_only()
    """,
)


def upgrade() -> None:
    op.create_table(
        "visits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("chief_complaint", sa.Text(), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "vitals",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('OPEN', 'COMPLETED')", name=op.f("ck_visits_status")),
        sa.CheckConstraint(
            "(status = 'COMPLETED') = (completed_at IS NOT NULL)",
            name=op.f("ck_visits_completed_has_time"),
        ),
        sa.CheckConstraint(
            "(completed_at IS NULL AND locked_at IS NULL)"
            " OR locked_at = completed_at + interval '24 hours'",
            name=op.f("ck_visits_locked_after_24_hours"),
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_visits_revision_positive")),
        *(
            sa.CheckConstraint(
                f"{column} IS NULL OR char_length({column}) <= {limit}",
                name=op.f(f"ck_visits_{column}_length"),
            )
            for column, limit in _TEXT_LIMITS.items()
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_visits_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f("fk_visits_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f("fk_visits_doctor_id_doctors")
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            ["appointments.id"],
            name=op.f("fk_visits_appointment_id_appointments"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_visits_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visits")),
        sa.UniqueConstraint("appointment_id", name=op.f("uq_visits_appointment_id")),
    )
    op.create_index(
        op.f("ix_visits_clinic_id_patient_id_started_at"),
        "visits",
        ["clinic_id", "patient_id", sa.text("started_at DESC"), sa.text("id DESC")],
    )

    op.create_table(
        "visit_addenda",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 5000", name=op.f("ck_visit_addenda_body_length")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_visit_addenda_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["visit_id"], ["visits.id"], name=op.f("fk_visit_addenda_visit_id_visits")
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"], ["users.id"], name=op.f("fk_visit_addenda_author_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visit_addenda")),
    )
    op.create_index(
        op.f("ix_visit_addenda_visit_id_created_at"),
        "visit_addenda",
        ["visit_id", "created_at"],
    )
    op.execute(_APPEND_ONLY_FUNCTION)
    for trigger in _APPEND_ONLY_TRIGGERS:
        op.execute(trigger)


def downgrade() -> None:
    # Dropping the table drops its triggers; the function goes after.
    op.drop_table("visit_addenda")
    op.execute("DROP FUNCTION IF EXISTS visit_addenda_append_only()")
    op.drop_table("visits")
