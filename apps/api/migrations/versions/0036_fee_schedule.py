"""the clinic's fee schedule (M6d-P1)

Spec billing R1-R12; FR-BIL-01; decision D8. Expand-only.

- ``clinic_services``: a clinic's services (name, kind, optional default price in paise, active,
  position); active names unique per clinic ignoring case (a partial unique index).
- ``doctor_service_prices``: a doctor's own price for one service, unique per pair.
- ``doctors.show_fee`` (default false): show the consultation price on the public profile (D8).

Data: every existing clinic gets *Consultation* and *Follow-up* without a default price (R2). A
doctor's M6c public fee (``doctors.fee_paise``) becomes their own *Consultation* price, and
``show_fee`` is set where there was one, so public profiles show the same fee as before.
``doctors.fee_paise`` stays (expand-only) and is no longer written.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRICE = "BETWEEN 0 AND 10000000"


def upgrade() -> None:
    s = "clinic_services"
    op.create_table(
        s,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("default_price_paise", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('CONSULTATION', 'FOLLOW_UP', 'PROCEDURE', 'OTHER')", name=op.f(f"ck_{s}_kind")
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 80", name=op.f(f"ck_{s}_name_length")),
        sa.CheckConstraint(
            f"default_price_paise IS NULL OR default_price_paise {_PRICE}",
            name=op.f(f"ck_{s}_price_range"),
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 100", name=op.f(f"ck_{s}_position_range")),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{s}_clinic_id_clinics")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{s}")),
    )
    op.create_index(
        f"uq_{s}_clinic_id_name",
        s,
        ["clinic_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("active"),
    )

    p = "doctor_service_prices"
    op.create_table(
        p,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"price_paise {_PRICE}", name=op.f(f"ck_{p}_price_range")),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{p}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["service_id"], ["clinic_services.id"], name=op.f(f"fk_{p}_service_id_clinic_services")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f(f"fk_{p}_doctor_id_doctors")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{p}")),
    )
    op.create_index(f"uq_{p}_service_id_doctor_id", p, ["service_id", "doctor_id"], unique=True)

    op.add_column(
        "doctors",
        sa.Column("show_fee", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # R2: the starting pair for every clinic; D8: the M6c public fee carried over.
    op.execute(
        "INSERT INTO clinic_services (id, clinic_id, name, kind, position, created_at, updated_at)"
        " SELECT gen_random_uuid(), c.id, v.name, v.kind, v.position, now(), now()"
        " FROM clinics c CROSS JOIN (VALUES ('Consultation', 'CONSULTATION', 1),"
        " ('Follow-up', 'FOLLOW_UP', 2)) AS v(name, kind, position)"
    )
    op.execute(
        "INSERT INTO doctor_service_prices"
        " (id, clinic_id, service_id, doctor_id, price_paise, created_at, updated_at)"
        " SELECT gen_random_uuid(), d.clinic_id, s.id, d.id, d.fee_paise, now(), now()"
        " FROM doctors d JOIN clinic_services s"
        " ON s.clinic_id = d.clinic_id AND s.kind = 'CONSULTATION'"
        " WHERE d.fee_paise IS NOT NULL"
    )
    op.execute("UPDATE doctors SET show_fee = true WHERE fee_paise IS NOT NULL")


def downgrade() -> None:
    op.drop_column("doctors", "show_fee")
    op.drop_table("doctor_service_prices")
    op.drop_table("clinic_services")
