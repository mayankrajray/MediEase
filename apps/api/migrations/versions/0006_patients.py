"""patients and the clinic's patient-code counter (M2-P1)

FR-PAT-01, 03, 04, 05, 06; spec patients §3 and R4; docs/DATA_MODEL.md "M2".

``clinics`` gains ``patient_code_prefix`` and ``next_patient_seq``. Existing clinics are
given a prefix derived from their name (this migration carries its own copy of the
derivation, so it keeps meaning the same thing whatever the application code later does)
and the counter starts at 1. The prefix is NOT NULL with no default: the application
always supplies it, and a silent default would hide a bug.

``patients`` is tenant-owned (``clinic_id``). Its indexes are the lookup design (FR-PAT-04):
the unique ``(clinic_id, code)`` serves code lookup, ``(clinic_id, phone_e164)`` serves the
phone lookup and duplicate check (families share phones, so it is not unique), and
``(clinic_id, lower(full_name) text_pattern_ops)`` serves case-insensitive name-prefix
lookup, which a plain index on ``full_name`` cannot.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-03
"""

from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORD = re.compile(r"[A-Za-z]+")


def _prefix_for(name: str) -> str:
    """Word initials, else the first two letters, else CL (a frozen copy of the domain rule)."""
    words = _WORD.findall(name)
    initials = "".join(word[0] for word in words[:4]).upper()
    if len(initials) >= 2:
        return initials
    letters = "".join(words).upper()
    return letters[:2] if len(letters) >= 2 else "CL"


def upgrade() -> None:
    op.add_column("clinics", sa.Column("patient_code_prefix", sa.Text(), nullable=True))
    op.add_column(
        "clinics",
        sa.Column("next_patient_seq", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    connection = op.get_bind()
    for clinic_id, name in connection.execute(sa.text("SELECT id, name FROM clinics")).all():
        connection.execute(
            sa.text("UPDATE clinics SET patient_code_prefix = :prefix WHERE id = :id"),
            {"prefix": _prefix_for(name), "id": clinic_id},
        )
    op.alter_column("clinics", "patient_code_prefix", nullable=False)
    op.create_check_constraint(
        op.f("ck_clinics_patient_code_prefix_format"),
        "clinics",
        "patient_code_prefix ~ '^[A-Z]{2,4}$'",
    )
    op.create_check_constraint(
        op.f("ck_clinics_next_patient_seq_positive"), "clinics", "next_patient_seq >= 1"
    )

    op.create_table(
        "patients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("phone_e164", sa.Text(), nullable=False),
        sa.Column("sex", sa.Text(), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("age_years_at_registration", sa.Integer(), nullable=True),
        sa.Column("registered_on", sa.Date(), nullable=False),
        sa.Column("guardian_name", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), server_default=sa.text("'en'"), nullable=False),
        sa.Column(
            "whatsapp_consent", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("sms_consent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("consent_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_recorded_by", sa.Uuid(), nullable=True),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sex IN ('FEMALE', 'MALE', 'OTHER', 'UNDISCLOSED')", name=op.f("ck_patients_sex")
        ),
        sa.CheckConstraint("language IN ('en', 'hi')", name=op.f("ck_patients_language")),
        sa.CheckConstraint(
            "(date_of_birth IS NOT NULL) <> (age_years_at_registration IS NOT NULL)",
            name=op.f("ck_patients_age_known"),
        ),
        sa.CheckConstraint(
            "age_years_at_registration IS NULL OR age_years_at_registration BETWEEN 0 AND 120",
            name=op.f("ck_patients_age_years_at_registration_range"),
        ),
        sa.CheckConstraint(
            "(NOT whatsapp_consent AND NOT sms_consent) OR consent_recorded_at IS NOT NULL",
            name=op.f("ck_patients_consent_recorded"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_patients_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["consent_recorded_by"],
            ["users.id"],
            name=op.f("fk_patients_consent_recorded_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_patients_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patients")),
        sa.UniqueConstraint("clinic_id", "code", name=op.f("uq_patients_clinic_id_code")),
    )
    op.create_index(
        op.f("ix_patients_clinic_id_phone_e164"), "patients", ["clinic_id", "phone_e164"]
    )
    op.create_index(
        op.f("ix_patients_clinic_id_lower_full_name"),
        "patients",
        ["clinic_id", sa.text("lower(full_name) text_pattern_ops")],
    )


def downgrade() -> None:
    op.drop_table("patients")
    op.drop_constraint(op.f("ck_clinics_next_patient_seq_positive"), "clinics", type_="check")
    op.drop_constraint(op.f("ck_clinics_patient_code_prefix_format"), "clinics", type_="check")
    op.drop_column("clinics", "next_patient_seq")
    op.drop_column("clinics", "patient_code_prefix")
