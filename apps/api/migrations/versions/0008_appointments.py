"""appointments and their status history (M3-P2)

FR-APT-03..05, FR-APT-07; spec appointments R3-R8, D10-D15; docs/DATA_MODEL.md "M3".
Expand-only.

``appointments`` holds one patient's place in one session: a ``slot_start`` in slot mode or a
``token_number`` in token mode, never both. The database backs the booking rules even if the code
were wrong (FR-APT-04): one active appointment per slot and per patient in a session (partial
unique indexes), and a token is unique in its session whether cancelled or not (R4).
``appointment_status_history`` is append-only, one row per status change (FR-APT-05).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = "'BOOKED', 'ARRIVED', 'IN_CONSULTATION', 'COMPLETED', 'NO_SHOW', 'CANCELLED'"
_SOURCES = "'FRONT_DESK', 'PHONE', 'WHATSAPP', 'PUBLIC_PAGE', 'WALK_IN'"
_REASONS = (
    "'PATIENT_REQUEST', 'CLINIC_REQUEST', 'DOCTOR_UNAVAILABLE', 'DUPLICATE', 'OTHER', 'RESCHEDULED'"
)
_ACTIVE = "status <> 'CANCELLED'"


def upgrade() -> None:
    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_number", sa.SmallInteger(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancel_note", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rescheduled_from_id", sa.Uuid(), nullable=True),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name=op.f("ck_appointments_status")),
        sa.CheckConstraint(f"source IN ({_SOURCES})", name=op.f("ck_appointments_source")),
        sa.CheckConstraint(
            f"cancel_reason IN ({_REASONS})", name=op.f("ck_appointments_cancel_reason")
        ),
        sa.CheckConstraint(
            "(slot_start IS NULL) <> (token_number IS NULL)", name=op.f("ck_appointments_one_place")
        ),
        sa.CheckConstraint(
            "token_number IS NULL OR token_number >= 1",
            name=op.f("ck_appointments_token_positive"),
        ),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancel_reason IS NOT NULL AND cancelled_at IS NOT NULL)",
            name=op.f("ck_appointments_cancelled_has_reason"),
        ),
        sa.CheckConstraint(
            "reason IS NULL OR char_length(reason) <= 120",
            name=op.f("ck_appointments_reason_length"),
        ),
        sa.CheckConstraint(
            "cancel_note IS NULL OR char_length(cancel_note) <= 200",
            name=op.f("ck_appointments_cancel_note_length"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_appointments_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_appointments_session_id_sessions")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f("fk_appointments_doctor_id_doctors")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f("fk_appointments_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(
            ["rescheduled_from_id"],
            ["appointments.id"],
            name=op.f("fk_appointments_rescheduled_from_id_appointments"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_appointments_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
        sa.UniqueConstraint(
            "session_id", "token_number", name=op.f("uq_appointments_session_id_token_number")
        ),
    )
    op.create_index(
        op.f("uq_appointments_session_id_slot_start_active"),
        "appointments",
        ["session_id", "slot_start"],
        unique=True,
        postgresql_where=sa.text(f"{_ACTIVE} AND slot_start IS NOT NULL"),
    )
    op.create_index(
        op.f("uq_appointments_session_id_patient_id_active"),
        "appointments",
        ["session_id", "patient_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE),
    )
    op.create_index(
        op.f("ix_appointments_clinic_id_doctor_id_status"),
        "appointments",
        ["clinic_id", "doctor_id", "status"],
    )
    op.create_index(
        op.f("ix_appointments_clinic_id_patient_id_created_at"),
        "appointments",
        ["clinic_id", "patient_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "appointment_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"from_status IN ({_STATUSES})", name=op.f("ck_appointment_status_history_from_status")
        ),
        sa.CheckConstraint(
            f"to_status IN ({_STATUSES})", name=op.f("ck_appointment_status_history_to_status")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["clinics.id"],
            name=op.f("fk_appointment_status_history_clinic_id_clinics"),
        ),
        sa.ForeignKeyConstraint(
            ["appointment_id"],
            ["appointments.id"],
            name=op.f("fk_appointment_status_history_appointment_id_appointments"),
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            name=op.f("fk_appointment_status_history_changed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointment_status_history")),
    )
    op.create_index(
        op.f("ix_appointment_status_history_appointment_id_changed_at"),
        "appointment_status_history",
        ["appointment_id", "changed_at"],
    )


def downgrade() -> None:
    op.drop_table("appointment_status_history")
    op.drop_table("appointments")
