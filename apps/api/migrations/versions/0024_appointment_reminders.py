"""appointment reminders, clinic reminder settings, bookings-to-move notifications (M6a-P8)

FR-APT-08 (decisions 1A-4A), FR-APT-09 (decision 6A). Expand-only.

- ``reminders``: kind and source ``APPOINTMENT``; ``appointment_id`` (set exactly for that source,
  and the kind follows the source); ``created_by`` nullable (the system); an index on
  ``appointment_id``.
- ``clinics``: ``reminder_evening_before`` (default true) and ``reminder_hours_before`` (0-6,
  default 2), for bookings made or moved from now on.
- ``notifications`` and ``notification_preferences``: the kind ``schedule.bookings_to_move``.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_KINDS = (
    "'appointment.booked', 'appointment.rescheduled', 'appointment.cancelled',"
    " 'appointment.arrived', 'message.failed', 'staff.joined'"
)
_NEW_KINDS = _OLD_KINDS + ", 'schedule.bookings_to_move'"


def _notification_kinds(kinds: str) -> None:
    for table in ("notifications", "notification_preferences"):
        name = op.f(f"ck_{table}_kind")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"kind IN ({kinds})")


def _reminder_checks(kinds: str, sources: str) -> None:
    for name, check in (("kind", kinds), ("source", sources)):
        constraint = op.f(f"ck_reminders_{name}")
        op.drop_constraint(constraint, "reminders", type_="check")
        op.create_check_constraint(constraint, "reminders", f"{name} IN ({check})")


def upgrade() -> None:
    op.add_column("reminders", sa.Column("appointment_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_reminders_appointment_id_appointments"),
        "reminders",
        "appointments",
        ["appointment_id"],
        ["id"],
    )
    op.alter_column("reminders", "created_by", existing_type=sa.Uuid(), nullable=True)
    _reminder_checks("'FOLLOW_UP', 'APPOINTMENT'", "'PRESCRIPTION', 'MANUAL', 'APPOINTMENT'")
    op.create_check_constraint(
        op.f("ck_reminders_appointment_id"),
        "reminders",
        "(source = 'APPOINTMENT') = (appointment_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_reminders_kind_source"),
        "reminders",
        "(kind = 'APPOINTMENT') = (source = 'APPOINTMENT')",
    )
    op.create_index("ix_reminders_appointment_id", "reminders", ["appointment_id"])

    op.add_column(
        "clinics",
        sa.Column(
            "reminder_evening_before", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.add_column(
        "clinics",
        sa.Column(
            "reminder_hours_before", sa.SmallInteger(), server_default=sa.text("2"), nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_clinics_reminder_hours_before_range"),
        "clinics",
        "reminder_hours_before BETWEEN 0 AND 6",
    )

    _notification_kinds(_NEW_KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'schedule.bookings_to_move'")
    op.execute("DELETE FROM notification_preferences WHERE kind = 'schedule.bookings_to_move'")
    _notification_kinds(_OLD_KINDS)

    op.drop_constraint(op.f("ck_clinics_reminder_hours_before_range"), "clinics", type_="check")
    op.drop_column("clinics", "reminder_hours_before")
    op.drop_column("clinics", "reminder_evening_before")

    # Appointment reminders and their messages and jobs go; follow-ups are untouched.
    op.execute(
        "DELETE FROM jobs WHERE kind = 'send_reminder' AND payload->>'reminder_id' IN"
        " (SELECT id::text FROM reminders WHERE kind = 'APPOINTMENT')"
    )
    op.execute(
        "DELETE FROM messages WHERE source_type = 'REMINDER' AND source_id IN"
        " (SELECT id FROM reminders WHERE kind = 'APPOINTMENT')"
    )
    op.execute("DELETE FROM reminders WHERE kind = 'APPOINTMENT'")
    op.drop_index("ix_reminders_appointment_id", table_name="reminders")
    op.drop_constraint(op.f("ck_reminders_kind_source"), "reminders", type_="check")
    op.drop_constraint(op.f("ck_reminders_appointment_id"), "reminders", type_="check")
    _reminder_checks("'FOLLOW_UP'", "'PRESCRIPTION', 'MANUAL'")
    op.alter_column("reminders", "created_by", existing_type=sa.Uuid(), nullable=False)
    op.drop_constraint(
        op.f("fk_reminders_appointment_id_appointments"), "reminders", type_="foreignkey"
    )
    op.drop_column("reminders", "appointment_id")
