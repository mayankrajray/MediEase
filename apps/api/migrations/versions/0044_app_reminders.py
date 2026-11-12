"""reminders for app users: two patient notice kinds and the SENT_IN_APP status (M7e-E4)

Spec web-push R40-R46. Expand-only.

- ``patient_notifications.kind`` and ``patient_notification_preferences.kind`` allow
  ``appointment.reminder`` and ``follow_up.due``.
- ``reminders.status`` allows ``SENT_IN_APP``: no WhatsApp consent, and the app account linked
  to the record was told instead.

Downgrade deletes the new kinds' notices and preferences, and turns ``SENT_IN_APP`` back into
``SKIPPED_NO_CONSENT`` (what it was for WhatsApp).

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_BEFORE = (
    "'booking.accepted', 'booking.declined', 'booking.proposed', 'booking.expired',"
    " 'appointment.confirmed', 'appointment.moved', 'appointment.cancelled',"
    " 'prescription.ready', 'medicine.due'"
)
_KINDS_AFTER = f"{_KINDS_BEFORE}, 'appointment.reminder', 'follow_up.due'"
_STATUS_BEFORE = "'SCHEDULED', 'SENT', 'CANCELLED', 'SKIPPED_NO_CONSENT', 'FAILED'"
_STATUS_AFTER = f"{_STATUS_BEFORE}, 'SENT_IN_APP'"


def _check(table: str, column: str, values: str) -> None:
    name = op.f(f"ck_{table}_{column}")
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, f"{column} IN ({values})")


def upgrade() -> None:
    _check("patient_notifications", "kind", _KINDS_AFTER)
    _check("patient_notification_preferences", "kind", _KINDS_AFTER)
    _check("reminders", "status", _STATUS_AFTER)


def downgrade() -> None:
    new = "('appointment.reminder', 'follow_up.due')"
    op.execute(f"DELETE FROM patient_notifications WHERE kind IN {new}")
    op.execute(f"DELETE FROM patient_notification_preferences WHERE kind IN {new}")
    op.execute("UPDATE reminders SET status = 'SKIPPED_NO_CONSENT' WHERE status = 'SENT_IN_APP'")
    _check("reminders", "status", _STATUS_BEFORE)
    _check("patient_notification_preferences", "kind", _KINDS_BEFORE)
    _check("patient_notifications", "kind", _KINDS_BEFORE)
