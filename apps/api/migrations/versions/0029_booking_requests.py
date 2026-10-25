"""booking requests, the soft hold and the clinic's request settings (M6b-P4)

Spec booking-requests R9-R27; ADR-0018; developer decisions 25 Oct 2026. Expand-only.

- ``booking_requests`` (tenant): a patient account's request for a slot (or a token session), with
  the contact phone, optional age and sex, an optional short reason, ``hold_expires_at`` (the soft
  hold, never past ``respond_by``), ``respond_by`` (the response deadline) and a staff override of
  the hold. One open (``PENDING``) request per account and session; no unique index on the slot.
- ``clinics``: ``request_hold_minutes`` (30-480, default 120) and ``request_requires_age_sex``.
- ``notifications`` and ``notification_preferences``: the kind ``booking.requested``.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_T = "booking_requests"
_OLD_KINDS = (
    "'appointment.booked', 'appointment.rescheduled', 'appointment.cancelled',"
    " 'appointment.arrived', 'message.failed', 'staff.joined', 'schedule.bookings_to_move'"
)
_NEW_KINDS = _OLD_KINDS + ", 'booking.requested'"


def _notification_kinds(kinds: str) -> None:
    for table in ("notifications", "notification_preferences"):
        name = op.f(f"ck_{table}_kind")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"kind IN ({kinds})")


def upgrade() -> None:
    t = _T
    op.create_table(
        t,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("contact_phone", sa.Text(), nullable=False),
        sa.Column("age_years", sa.SmallInteger(), nullable=True),
        sa.Column("sex", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("respond_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hold_overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hold_overridden_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PENDING')", name=op.f(f"ck_{t}_status")),
        sa.CheckConstraint(
            "sex IN ('FEMALE', 'MALE', 'OTHER', 'UNDISCLOSED')", name=op.f(f"ck_{t}_sex")
        ),
        sa.CheckConstraint(
            "age_years IS NULL OR age_years BETWEEN 0 AND 120", name=op.f(f"ck_{t}_age_range")
        ),
        sa.CheckConstraint(
            "reason IS NULL OR char_length(reason) BETWEEN 1 AND 200",
            name=op.f(f"ck_{t}_reason_length"),
        ),
        sa.CheckConstraint(
            "hold_expires_at <= respond_by", name=op.f(f"ck_{t}_hold_within_deadline")
        ),
        sa.CheckConstraint(
            "(hold_overridden_at IS NULL) = (hold_overridden_by IS NULL)",
            name=op.f(f"ck_{t}_override_together"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f(f"fk_{t}_doctor_id_doctors")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f(f"fk_{t}_session_id_sessions")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f(f"fk_{t}_account_id_patient_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["hold_overridden_by"], ["users.id"], name=op.f(f"fk_{t}_hold_overridden_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
    )
    op.create_index(
        "uq_booking_requests_account_session_pending",
        t,
        ["account_id", "session_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(op.f(f"ix_{t}_session_id"), t, ["session_id"])
    op.create_index(
        op.f(f"ix_{t}_clinic_id_status_created_at"), t, ["clinic_id", "status", "created_at"]
    )
    op.create_index(op.f(f"ix_{t}_account_id"), t, ["account_id"])

    op.add_column(
        "clinics",
        sa.Column(
            "request_hold_minutes", sa.SmallInteger(), server_default=sa.text("120"), nullable=False
        ),
    )
    op.add_column(
        "clinics",
        sa.Column(
            "request_requires_age_sex",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_clinics_request_hold_minutes_range"),
        "clinics",
        "request_hold_minutes BETWEEN 30 AND 480",
    )
    _notification_kinds(_NEW_KINDS)


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE kind = 'booking.requested'")
    op.execute("DELETE FROM notification_preferences WHERE kind = 'booking.requested'")
    _notification_kinds(_OLD_KINDS)
    op.drop_constraint(op.f("ck_clinics_request_hold_minutes_range"), "clinics", type_="check")
    op.drop_column("clinics", "request_requires_age_sex")
    op.drop_column("clinics", "request_hold_minutes")
    op.drop_index(op.f(f"ix_{_T}_account_id"), table_name=_T)
    op.drop_index(op.f(f"ix_{_T}_clinic_id_status_created_at"), table_name=_T)
    op.drop_index(op.f(f"ix_{_T}_session_id"), table_name=_T)
    op.drop_index("uq_booking_requests_account_session_pending", table_name=_T)
    op.drop_table(_T)
