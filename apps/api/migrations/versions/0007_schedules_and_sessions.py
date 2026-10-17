"""doctor schedules, schedule exceptions, sessions and the clinic's booking mode (M3-P1)

FR-APT-01, FR-APT-02; spec appointments R1-R4, R14-R20; docs/DATA_MODEL.md "M3". Expand-only.

``clinics.booking_mode`` defaults to TOKENS for existing clinics (many small clinics run tokens).
``doctor_schedules`` holds weekly blocks as wall-clock times with a validity window, so replacing
a schedule closes the old blocks instead of deleting history. ``schedule_exceptions`` holds
whole-day leave (at most one per doctor and date) and extra blocks. ``sessions`` are generated
lazily per clinic-local date; ``UNIQUE (doctor_id, starts_at)`` makes generation idempotent and
``booked_count BETWEEN 0 AND capacity`` keeps overbooking out (decision D6).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SLOT_RANGE = "slot_minutes IS NULL OR slot_minutes BETWEEN 5 AND 120"
_CAPACITY_RANGE = "capacity IS NULL OR capacity BETWEEN 1 AND 500"


def _tenant_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
    ]


def _timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _keys(table: str) -> list[sa.Constraint]:
    return [
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{table}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f(f"fk_{table}_doctor_id_doctors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def upgrade() -> None:
    op.add_column(
        "clinics",
        sa.Column("booking_mode", sa.Text(), server_default=sa.text("'TOKENS'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_clinics_booking_mode"), "clinics", "booking_mode IN ('SLOTS', 'TOKENS')"
    )

    op.create_table(
        "doctor_schedules",
        *_tenant_columns(),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("slot_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("capacity", sa.SmallInteger(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name=op.f("ck_doctor_schedules_weekday_range")
        ),
        sa.CheckConstraint("start_time <> end_time", name=op.f("ck_doctor_schedules_not_empty")),
        sa.CheckConstraint(_SLOT_RANGE, name=op.f("ck_doctor_schedules_slot_range")),
        sa.CheckConstraint(_CAPACITY_RANGE, name=op.f("ck_doctor_schedules_capacity_range")),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_doctor_schedules_valid_window"),
        ),
        *_keys("doctor_schedules"),
    )
    op.create_index(
        op.f("ix_doctor_schedules_clinic_id_doctor_id"),
        "doctor_schedules",
        ["clinic_id", "doctor_id"],
    )

    op.create_table(
        "schedule_exceptions",
        *_tenant_columns(),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("slot_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("capacity", sa.SmallInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('LEAVE', 'EXTRA')", name=op.f("ck_schedule_exceptions_kind")),
        sa.CheckConstraint(
            "(kind = 'LEAVE' AND start_time IS NULL AND end_time IS NULL"
            " AND slot_minutes IS NULL AND capacity IS NULL)"
            " OR (kind = 'EXTRA' AND start_time IS NOT NULL AND end_time IS NOT NULL"
            " AND start_time <> end_time)",
            name=op.f("ck_schedule_exceptions_shape_by_kind"),
        ),
        sa.CheckConstraint(_SLOT_RANGE, name=op.f("ck_schedule_exceptions_slot_range")),
        sa.CheckConstraint(_CAPACITY_RANGE, name=op.f("ck_schedule_exceptions_capacity_range")),
        *_keys("schedule_exceptions"),
    )
    op.create_index(
        op.f("ix_schedule_exceptions_clinic_id_doctor_id_on_date"),
        "schedule_exceptions",
        ["clinic_id", "doctor_id", "on_date"],
    )
    op.create_index(
        op.f("uq_schedule_exceptions_doctor_id_on_date_leave"),
        "schedule_exceptions",
        ["doctor_id", "on_date"],
        unique=True,
        postgresql_where=sa.text("kind = 'LEAVE'"),
    )

    op.create_table(
        "sessions",
        *_tenant_columns(),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("slot_minutes", sa.SmallInteger(), nullable=True),
        sa.Column("capacity", sa.SmallInteger(), nullable=False),
        sa.Column("booked_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_token", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'OPEN'"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("mode IN ('SLOTS', 'TOKENS')", name=op.f("ck_sessions_mode")),
        sa.CheckConstraint(
            "status IN ('OPEN', 'CLOSED', 'CANCELLED')", name=op.f("ck_sessions_status")
        ),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_sessions_ends_after_start")),
        sa.CheckConstraint(
            "booked_count BETWEEN 0 AND capacity", name=op.f("ck_sessions_booked_within_capacity")
        ),
        sa.CheckConstraint("capacity BETWEEN 1 AND 500", name=op.f("ck_sessions_capacity_range")),
        sa.CheckConstraint("next_token >= 1", name=op.f("ck_sessions_next_token_positive")),
        sa.CheckConstraint(
            "(mode = 'SLOTS') = (slot_minutes IS NOT NULL)",
            name=op.f("ck_sessions_slot_minutes_by_mode"),
        ),
        *_keys("sessions"),
        sa.UniqueConstraint("doctor_id", "starts_at", name=op.f("uq_sessions_doctor_id_starts_at")),
    )
    op.create_index(
        op.f("ix_sessions_clinic_id_on_date_doctor_id"),
        "sessions",
        ["clinic_id", "on_date", "doctor_id"],
    )


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("schedule_exceptions")
    op.drop_table("doctor_schedules")
    op.drop_constraint(op.f("ck_clinics_booking_mode"), "clinics", type_="check")
    op.drop_column("clinics", "booking_mode")
