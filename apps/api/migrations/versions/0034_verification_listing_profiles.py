"""clinic and doctor verification, the directory listing and profile fields (M6c-P3, P4, P5)

Spec clinic-onboarding R41-R58, discovery R1-R12. Expand-only.

- ``clinics``: ``verified_at``, ``verified_by``, ``verification_source``, ``application_id``;
  ``listed``, ``listed_at`` (only when verified, CHECK); ``search_indexing`` (default true).
- ``doctors``: ``verified_at``, ``verified_by``, ``verification_source``; ``visible``;
  ``languages``, ``fee_paise`` (0-1 000 000).
- ``booking_requests.decline_reason`` gains ``CLINIC_UNAVAILABLE`` (P4: a suspended clinic's open
  requests are withdrawn).

Existing clinics stay unverified (FR-ONB-06); ``make seed`` verifies the demo clinics.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCES = "verification_source IN ('APPLICATION', 'OPS_CHECK')"
_REASONS_BEFORE = (
    "'TIME_UNAVAILABLE', 'DOCTOR_UNAVAILABLE', 'PLEASE_CALL', 'NOT_ONLINE', 'DUPLICATE', 'OTHER',"
    " 'PATIENT_DECLINED'"
)
_REASONS_AFTER = _REASONS_BEFORE + ", 'CLINIC_UNAVAILABLE'"


def _verification(table: str) -> None:
    op.add_column(table, sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("verified_by", sa.Uuid(), nullable=True))
    op.add_column(table, sa.Column("verification_source", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f(f"fk_{table}_verified_by_users"), table, "users", ["verified_by"], ["id"]
    )
    op.create_check_constraint(op.f(f"ck_{table}_verification_source"), table, _SOURCES)


def _decline_reasons(values: str) -> None:
    op.drop_constraint(
        op.f("ck_booking_requests_decline_reason"), "booking_requests", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_booking_requests_decline_reason"),
        "booking_requests",
        f"decline_reason IN ({values})",
    )


def upgrade() -> None:
    _verification("clinics")
    op.add_column("clinics", sa.Column("application_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_clinics_application_id_clinic_applications"),
        "clinics",
        "clinic_applications",
        ["application_id"],
        ["id"],
    )
    op.add_column(
        "clinics",
        sa.Column("listed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("clinics", sa.Column("listed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "clinics",
        sa.Column("search_indexing", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_clinics_listed_verified"), "clinics", "NOT listed OR verified_at IS NOT NULL"
    )

    _verification("doctors")
    op.add_column(
        "doctors",
        sa.Column("visible", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "doctors",
        sa.Column(
            "languages", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
    )
    op.add_column("doctors", sa.Column("fee_paise", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_doctors_fee_paise_range"),
        "doctors",
        "fee_paise IS NULL OR fee_paise BETWEEN 0 AND 1000000",
    )
    _decline_reasons(_REASONS_AFTER)


def downgrade() -> None:
    op.execute(
        "UPDATE booking_requests SET decline_reason = 'OTHER'"
        " WHERE decline_reason = 'CLINIC_UNAVAILABLE'"
    )
    _decline_reasons(_REASONS_BEFORE)
    op.drop_constraint(op.f("ck_doctors_fee_paise_range"), "doctors", type_="check")
    for name in ("fee_paise", "languages", "visible"):
        op.drop_column("doctors", name)
    op.drop_constraint(op.f("ck_clinics_listed_verified"), "clinics", type_="check")
    for name in ("search_indexing", "listed_at", "listed"):
        op.drop_column("clinics", name)
    op.drop_constraint(
        op.f("fk_clinics_application_id_clinic_applications"), "clinics", type_="foreignkey"
    )
    op.drop_column("clinics", "application_id")
    for table in ("clinics", "doctors"):
        op.drop_constraint(op.f(f"ck_{table}_verification_source"), table, type_="check")
        op.drop_constraint(op.f(f"fk_{table}_verified_by_users"), table, type_="foreignkey")
        for name in ("verification_source", "verified_by", "verified_at"):
            op.drop_column(table, name)
