"""clinic applications (M6c-P1)

Spec clinic-onboarding R1-R23; ADR-0020; developer approval 26 Oct 2026. Expand-only.

- ``clinic_applications`` and ``clinic_application_doctors``: platform tables (no clinic until
  approval). References come from ``clinic_application_reference_seq``.
- ``audit_events.actor_type`` gains ``APPLICANT`` (no user, no clinic).
- ``ck_jobs_system_kind`` gains ``send_application_email`` and ``purge_applications``.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTORS_BEFORE = "'STAFF', 'OPS', 'PATIENT_LINK', 'SYSTEM', 'PATIENT'"
_ACTORS_AFTER = "'STAFF', 'OPS', 'PATIENT_LINK', 'SYSTEM', 'PATIENT', 'APPLICANT'"
_SYSTEM_BEFORE = (
    "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages',"
    " 'schedule_medicine_due', 'schedule_no_shows', 'schedule_request_expiry', 'send_auth_email'"
)
_SYSTEM_AFTER = (
    "'process_webhook_event', 'purge_applications', 'purge_expired_auth_and_links',"
    " 'reconcile_messages', 'schedule_medicine_due', 'schedule_no_shows',"
    " 'schedule_request_expiry', 'send_application_email', 'send_auth_email'"
)


def _actors(values: str) -> None:
    op.drop_constraint(op.f("ck_audit_events_actor_type"), "audit_events", type_="check")
    op.create_check_constraint(
        op.f("ck_audit_events_actor_type"), "audit_events", f"actor_type IN ({values})"
    )


def _system_kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_jobs_system_kind"), "jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_jobs_system_kind"), "jobs", f"(clinic_id IS NULL) = (kind IN ({kinds}))"
    )


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("clinic_application_reference_seq")))
    a = "clinic_applications"
    op.create_table(
        a,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("clinic_name", sa.Text(), nullable=False),
        sa.Column("address_line", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("pincode", sa.Text(), nullable=False),
        sa.Column("clinic_phone_e164", sa.Text(), nullable=False),
        sa.Column("specialties", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("owner_name", sa.Text(), nullable=False),
        sa.Column("owner_phone_e164", sa.Text(), nullable=False),
        sa.Column("owner_email", sa.Text(), nullable=False),
        sa.Column("owner_practises", sa.Boolean(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirm_digest", sa.Text(), nullable=True),
        sa.Column(
            "duplicate_of",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("ip_hash", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('CLINIC', 'SOLO_DOCTOR')", name=op.f(f"ck_{a}_kind")),
        sa.CheckConstraint(
            "status IN ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED')",
            name=op.f(f"ck_{a}_status"),
        ),
        sa.CheckConstraint("pincode ~ '^[1-9][0-9]{5}$'", name=op.f(f"ck_{a}_pincode_format")),
        sa.CheckConstraint(
            "email_verified_at IS NULL OR confirm_digest IS NULL",
            name=op.f(f"ck_{a}_confirmed_no_digest"),
        ),
        sa.CheckConstraint(
            "status = 'PENDING' OR email_verified_at IS NOT NULL",
            name=op.f(f"ck_{a}_reviewed_confirmed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{a}")),
        sa.UniqueConstraint("reference", name=op.f(f"uq_{a}_reference")),
        sa.UniqueConstraint("confirm_digest", name=op.f(f"uq_{a}_confirm_digest")),
    )
    op.create_index("ix_clinic_applications_owner_email", a, ["owner_email"])
    op.create_index("ix_clinic_applications_owner_phone_e164", a, ["owner_phone_e164"])
    op.create_index("ix_clinic_applications_ip_hash", a, ["ip_hash"])
    op.create_index("ix_clinic_applications_submitted_at", a, ["submitted_at"])

    d = "clinic_application_doctors"
    op.create_table(
        d,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qualification", sa.Text(), nullable=False),
        sa.Column("registration_council", sa.Text(), nullable=False),
        sa.Column("registration_number", sa.Text(), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False),
        sa.Column("certificate_key", sa.Text(), nullable=False),
        sa.Column("certificate_content_type", sa.Text(), nullable=False),
        sa.Column("certificate_size", sa.Integer(), nullable=False),
        sa.Column("certificate_sha256", sa.Text(), nullable=False),
        sa.CheckConstraint("position BETWEEN 1 AND 10", name=op.f(f"ck_{d}_position_range")),
        sa.CheckConstraint(
            "certificate_size BETWEEN 1 AND 5242880", name=op.f(f"ck_{d}_certificate_size_range")
        ),
        sa.CheckConstraint(
            "certificate_content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name=op.f(f"ck_{d}_certificate_content_type"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["clinic_applications.id"],
            name=op.f(f"fk_{d}_application_id_clinic_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{d}")),
        sa.UniqueConstraint(
            "application_id", "position", name=op.f(f"uq_{d}_application_id_position")
        ),
        sa.UniqueConstraint(
            "application_id",
            "registration_council",
            "registration_number",
            name="uq_clinic_application_doctors_registration",
        ),
    )
    op.create_index(
        "ix_clinic_application_doctors_registration",
        d,
        ["registration_council", "registration_number"],
    )
    _actors(_ACTORS_AFTER)
    _system_kinds(_SYSTEM_AFTER)


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE kind IN ('send_application_email', 'purge_applications')")
    _system_kinds(_SYSTEM_BEFORE)
    # Refused while applicant audit rows exist: audit_events is append-only (FR-AUD-02).
    _actors(_ACTORS_BEFORE)
    op.drop_index(
        "ix_clinic_application_doctors_registration", table_name="clinic_application_doctors"
    )
    op.drop_table("clinic_application_doctors")
    for index in ("owner_email", "owner_phone_e164", "ip_hash", "submitted_at"):
        op.drop_index(f"ix_clinic_applications_{index}", table_name="clinic_applications")
    op.drop_table("clinic_applications")
    op.execute(sa.schema.DropSequence(sa.Sequence("clinic_application_reference_seq")))
