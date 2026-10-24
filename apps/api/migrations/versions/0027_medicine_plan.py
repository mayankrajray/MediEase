"""the medicine plan: frequency patterns, duration kinds, start day, slot times, reminders (M6b-P3)

Prescriptions spec R21-R24; patient portal spec R28-R40; developer decisions D1, D3, D6.

- ``prescription_items.frequency``: the fixed list of six patterns becomes the rule in
  ``domain/prescriptions/schedule.py``: any 3- or 4-slot pattern of 0 and 1 with at least one 1,
  or SOS, ONCE, CUSTOM. Every value the old CHECK allowed is still allowed.
- ``prescription_items.duration_kind``: DAYS (with ``duration_days``), UNTIL_REVIEW, ONGOING;
  null = not stated. **No backfill**: issued rows are immutable (``prescription_items_frozen``),
  so a row from before this migration keeps a null kind and is read as DAYS when it has days.
- ``prescriptions.starts_on``: the doctor's chosen first day; null = the issue day (no backfill,
  for the same reason).
- ``patient_accounts.morning_time`` .. ``night_time``: the person's times of day (defaults 08:00,
  14:00, 18:00, 21:00), 05:00-23:30 and in the order of the day.
- ``medicine_reminder_prefs``: tenant data; one account's reminder choice per version, line and
  slot. Stored only (delivery is M6b-P6). ``item_id`` has no foreign key on purpose: the items
  of an issued version can never be deleted (``prescription_items_frozen``), and a key would put
  a second, non-trigger refusal in front of that trigger (AC1's TRUNCATE check).

Adding columns and replacing CHECKs fires no row trigger. Expand-only apart from the frequency
CHECK, which only widens.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ITEMS = "prescription_items"
_OLD_FREQUENCIES = "'1-0-0', '0-1-0', '0-0-1', '1-0-1', '1-1-1', '1-1-1-1', 'SOS', 'ONCE', 'CUSTOM'"
_FREQUENCY_RULE = (
    "frequency IN ('SOS', 'ONCE', 'CUSTOM')"
    " OR (frequency ~ '^[01](-[01]){2,3}$' AND strpos(frequency, '1') > 0)"
)
_SLOT_TIMES = (
    ("morning_time", "08:00"),
    ("afternoon_time", "14:00"),
    ("evening_time", "18:00"),
    ("night_time", "21:00"),
)


def upgrade() -> None:
    op.drop_constraint(op.f(f"ck_{_ITEMS}_frequency"), _ITEMS, type_="check")
    op.create_check_constraint(op.f(f"ck_{_ITEMS}_frequency"), _ITEMS, _FREQUENCY_RULE)

    op.add_column(_ITEMS, sa.Column("duration_kind", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f(f"ck_{_ITEMS}_duration_kind"),
        _ITEMS,
        "duration_kind IN ('DAYS', 'UNTIL_REVIEW', 'ONGOING')",
    )
    op.create_check_constraint(
        op.f(f"ck_{_ITEMS}_duration_days_with_kind"),
        _ITEMS,
        "duration_kind IS NULL OR (duration_kind = 'DAYS') = (duration_days IS NOT NULL)",
    )

    op.add_column("prescriptions", sa.Column("starts_on", sa.Date(), nullable=True))

    for column, default in _SLOT_TIMES:
        op.add_column(
            "patient_accounts",
            sa.Column(column, sa.Time(), server_default=sa.text(f"'{default}'"), nullable=False),
        )
    op.create_check_constraint(
        op.f("ck_patient_accounts_slot_times_in_order"),
        "patient_accounts",
        "morning_time >= '05:00' AND morning_time < afternoon_time"
        " AND afternoon_time < evening_time AND evening_time < night_time"
        " AND night_time <= '23:30'",
    )

    t = "medicine_reminder_prefs"
    op.create_table(
        t,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("prescription_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("remind_at", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "slot IN ('MORNING', 'AFTERNOON', 'EVENING', 'NIGHT')", name=op.f(f"ck_{t}_slot")
        ),
        sa.CheckConstraint(
            "remind_at IS NULL OR remind_at BETWEEN '05:00' AND '23:30'",
            name=op.f(f"ck_{t}_remind_at_range"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f(f"fk_{t}_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f(f"fk_{t}_account_id_patient_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["prescription_id"],
            ["prescriptions.id"],
            name=op.f(f"fk_{t}_prescription_id_prescriptions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint(
            "account_id",
            "prescription_id",
            "item_id",
            "slot",
            name=op.f(f"uq_{t}_line_slot"),
        ),
    )
    op.create_index(op.f(f"ix_{t}_clinic_id_patient_id"), t, ["clinic_id", "patient_id"])


def downgrade() -> None:
    t = "medicine_reminder_prefs"
    op.drop_index(op.f(f"ix_{t}_clinic_id_patient_id"), table_name=t)
    op.drop_table(t)
    op.drop_constraint(
        op.f("ck_patient_accounts_slot_times_in_order"), "patient_accounts", type_="check"
    )
    for column, _ in reversed(_SLOT_TIMES):
        op.drop_column("patient_accounts", column)
    op.drop_column("prescriptions", "starts_on")
    op.drop_constraint(op.f(f"ck_{_ITEMS}_duration_days_with_kind"), _ITEMS, type_="check")
    op.drop_constraint(op.f(f"ck_{_ITEMS}_duration_kind"), _ITEMS, type_="check")
    op.drop_column(_ITEMS, "duration_kind")
    # Narrowing back fails while a row holds a pattern the old list lacks, as it should.
    op.drop_constraint(op.f(f"ck_{_ITEMS}_frequency"), _ITEMS, type_="check")
    op.create_check_constraint(
        op.f(f"ck_{_ITEMS}_frequency"), _ITEMS, f"frequency IN ({_OLD_FREQUENCIES})"
    )
