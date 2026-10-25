"""answering booking requests: accept, decline, propose, expiry (M6b-P5)

Spec booking-requests R31-R52; developer approval 26 Oct 2026. Expand-only.

- ``booking_requests``: the statuses ``PROPOSED``, ``ACCEPTED``, ``DECLINED``, ``EXPIRED``; the
  chosen record and the appointment; the staff member's first answer (``answered_at``/``by``);
  when and by whom it became final (``decided_at``, ``decided_by_type``); the decline reason and
  the staff-only note; a proposal's original session and slot. The one-open-request index now
  covers both open states (``PENDING``, ``PROPOSED``).
- ``patient_account_links.method``: ``BOOKING`` (FR-PRT-06 a).
- ``ck_jobs_system_kind``: ``schedule_request_expiry`` (the 5-minute sweep).

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_T = "booking_requests"
_UQ = "uq_booking_requests_account_session_pending"
_OLD_SYSTEM = (
    "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages',"
    " 'schedule_no_shows', 'send_auth_email'"
)
_NEW_SYSTEM = (
    "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages',"
    " 'schedule_no_shows', 'schedule_request_expiry', 'send_auth_email'"
)
_REASONS = (
    "'TIME_UNAVAILABLE', 'DOCTOR_UNAVAILABLE', 'PLEASE_CALL', 'NOT_ONLINE', 'DUPLICATE', 'OTHER',"
    " 'PATIENT_DECLINED'"
)
_NEW_CHECKS = (
    ("decided_by_type", "decided_by_type IN ('STAFF', 'PATIENT', 'SYSTEM')"),
    ("decline_reason", f"decline_reason IN ({_REASONS})"),
    ("decline_note_length", "decline_note IS NULL OR char_length(decline_note) BETWEEN 1 AND 200"),
    ("decided_when_final", "(status IN ('PENDING', 'PROPOSED')) = (decided_at IS NULL)"),
    ("accepted_has_appointment", "(status = 'ACCEPTED') = (appointment_id IS NOT NULL)"),
    ("declined_has_reason", "(status = 'DECLINED') = (decline_reason IS NOT NULL)"),
)


def _check(table: str, name: str, condition: str) -> None:
    constraint = op.f(f"ck_{table}_{name}")
    op.drop_constraint(constraint, table, type_="check")
    op.create_check_constraint(constraint, table, condition)


def _open_index(statuses: str) -> None:
    op.drop_index(_UQ, table_name=_T)
    op.create_index(
        _UQ,
        _T,
        ["account_id", "session_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({statuses})"),
    )


def upgrade() -> None:
    t = _T
    for name, kind in (
        ("patient_id", sa.Uuid()),
        ("appointment_id", sa.Uuid()),
        ("answered_at", sa.DateTime(timezone=True)),
        ("answered_by", sa.Uuid()),
        ("decided_at", sa.DateTime(timezone=True)),
        ("decided_by_type", sa.Text()),
        ("decline_reason", sa.Text()),
        ("decline_note", sa.Text()),
        ("original_session_id", sa.Uuid()),
        ("original_slot_start", sa.DateTime(timezone=True)),
    ):
        op.add_column(t, sa.Column(name, kind, nullable=True))
    for column, target in (
        ("patient_id", "patients"),
        ("appointment_id", "appointments"),
        ("answered_by", "users"),
        ("original_session_id", "sessions"),
    ):
        op.create_foreign_key(op.f(f"fk_{t}_{column}_{target}"), t, target, [column], ["id"])
    _check(t, "status", "status IN ('PENDING', 'PROPOSED', 'ACCEPTED', 'DECLINED', 'EXPIRED')")
    for name, condition in _NEW_CHECKS:
        op.create_check_constraint(op.f(f"ck_{t}_{name}"), t, condition)
    _open_index("'PENDING', 'PROPOSED'")
    _check("patient_account_links", "method", "method IN ('INVITE', 'RX_LINK', 'BOOKING')")
    _check("jobs", "system_kind", f"(clinic_id IS NULL) = (kind IN ({_NEW_SYSTEM}))")


def downgrade() -> None:
    t = _T
    op.execute(
        "DELETE FROM jobs WHERE kind IN ('schedule_request_expiry', 'expire_booking_requests')"
    )
    _check("jobs", "system_kind", f"(clinic_id IS NULL) = (kind IN ({_OLD_SYSTEM}))")
    op.execute("DELETE FROM patient_account_links WHERE method = 'BOOKING'")
    _check("patient_account_links", "method", "method IN ('INVITE', 'RX_LINK')")
    op.execute(f"DELETE FROM {t} WHERE status <> 'PENDING'")
    _open_index("'PENDING'")
    for name, _ in _NEW_CHECKS:
        op.drop_constraint(op.f(f"ck_{t}_{name}"), t, type_="check")
    _check(t, "status", "status IN ('PENDING')")
    for column, target in (
        ("patient_id", "patients"),
        ("appointment_id", "appointments"),
        ("answered_by", "users"),
        ("original_session_id", "sessions"),
    ):
        op.drop_constraint(op.f(f"fk_{t}_{column}_{target}"), t, type_="foreignkey")
    for name in (
        "patient_id",
        "appointment_id",
        "answered_at",
        "answered_by",
        "decided_at",
        "decided_by_type",
        "decline_reason",
        "decline_note",
        "original_session_id",
        "original_slot_start",
    ):
        op.drop_column(t, name)
