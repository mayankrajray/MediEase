"""prescription uploads and their processing jobs (M7b-P6)

Spec prescription-uploads §3, R1-R19; FR-UPL-01..05, NFR-20; ADR-0023. Expand-only.

- ``prescription_uploads``: platform data owned by a patient account. ``clinic_id`` and the
  prescription are set only when the upload is verified, so it is not a tenant table until then
  and never appears in a clinic's reads. CHECKs keep each state's fields consistent (the file key
  only while the file is being checked, the verification fields exactly when verified, a
  rejection code exactly when rejected, the candidate only while the last-4 check is pending).
- ``ck_jobs_system_kind`` gains ``process_prescription_upload`` and ``purge_prescription_uploads``
  (an upload belongs to no clinic while it is processed).

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SYSTEM_BEFORE = (
    "'process_webhook_event', 'purge_applications', 'purge_expired_auth_and_links',"
    " 'reconcile_messages', 'schedule_medicine_due', 'schedule_no_shows',"
    " 'schedule_request_expiry', 'send_application_email', 'send_auth_email'"
)
_SYSTEM_AFTER = (
    "'process_prescription_upload', 'process_webhook_event', 'purge_applications',"
    " 'purge_expired_auth_and_links', 'purge_prescription_uploads', 'reconcile_messages',"
    " 'schedule_medicine_due', 'schedule_no_shows', 'schedule_request_expiry',"
    " 'send_application_email', 'send_auth_email'"
)
_STATES = "'QUARANTINED', 'SCANNING', 'EXTRACTING', 'NEEDS_CHALLENGE', 'VERIFIED', 'REJECTED'"
_FILE_STATES = "'QUARANTINED', 'SCANNING', 'EXTRACTING'"
_REJECTIONS = (
    "'UPL_INFECTED', 'UPL_SCAN_UNAVAILABLE', 'UPL_NO_IDENTIFIER', 'UPL_AMBIGUOUS',"
    " 'UPL_UNREADABLE', 'UPL_LOCKED', 'UPL_ABANDONED', 'UPL_EXPIRED', 'UPL_WITHDRAWN',"
    " 'UPL_FILE_MISSING'"
)


def _system_kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_jobs_system_kind"), "jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_jobs_system_kind"), "jobs", f"(clinic_id IS NULL) = (kind IN ({kinds}))"
    )


def upgrade() -> None:
    t = "prescription_uploads"
    op.create_table(
        t,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("quarantine_key", sa.Text(), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("clinic_id", sa.Uuid(), nullable=True),
        sa.Column("prescription_id", sa.Uuid(), nullable=True),
        sa.Column("access", sa.Text(), nullable=True),
        sa.Column("selected_id", sa.Uuid(), nullable=True),
        sa.Column("rejection_code", sa.Text(), nullable=True),
        sa.Column(
            "failed_challenges", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("source IN ('FILE', 'CODE')", name=op.f(f"ck_{t}_source")),
        sa.CheckConstraint(f"state IN ({_STATES})", name=op.f(f"ck_{t}_state")),
        sa.CheckConstraint("access IN ('OWN', 'REPRESENTATIVE')", name=op.f(f"ck_{t}_access")),
        sa.CheckConstraint(f"rejection_code IN ({_REJECTIONS})", name=op.f(f"ck_{t}_rejection")),
        sa.CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name=op.f(f"ck_{t}_content_type"),
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 10485760", name=op.f(f"ck_{t}_size_bytes_range")
        ),
        sa.CheckConstraint(
            "failed_challenges BETWEEN 0 AND 5", name=op.f(f"ck_{t}_failed_challenges_range")
        ),
        sa.CheckConstraint(
            "(source = 'FILE') = (content_type IS NOT NULL AND size_bytes IS NOT NULL"
            " AND sha256 IS NOT NULL)",
            name=op.f(f"ck_{t}_file_described"),
        ),
        sa.CheckConstraint(
            f"quarantine_key IS NULL OR (source = 'FILE' AND state IN ({_FILE_STATES}))",
            name=op.f(f"ck_{t}_file_only_while_checked"),
        ),
        sa.CheckConstraint(
            "(state = 'VERIFIED') = (clinic_id IS NOT NULL AND prescription_id IS NOT NULL"
            " AND access IS NOT NULL AND verified_at IS NOT NULL AND expires_at IS NOT NULL)",
            name=op.f(f"ck_{t}_verified_is_complete"),
        ),
        sa.CheckConstraint(
            "selected_id IS NULL OR state = 'VERIFIED'", name=op.f(f"ck_{t}_selected_if_verified")
        ),
        sa.CheckConstraint(
            "(state = 'REJECTED') = (rejection_code IS NOT NULL)",
            name=op.f(f"ck_{t}_rejected_has_code"),
        ),
        sa.CheckConstraint(
            "(state = 'NEEDS_CHALLENGE') = (candidate_id IS NOT NULL)",
            name=op.f(f"ck_{t}_candidate_while_challenged"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["patient_accounts.id"],
            name=op.f(f"fk_{t}_account_id_patient_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["prescription_id"],
            ["prescriptions.id"],
            name=op.f(f"fk_{t}_prescription_id_prescriptions"),
        ),
        sa.ForeignKeyConstraint(
            ["selected_id"], ["prescriptions.id"], name=op.f(f"fk_{t}_selected_id_prescriptions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint("quarantine_key", name=op.f(f"uq_{t}_quarantine_key")),
    )
    op.create_index(
        op.f(f"ix_{t}_account_id_created_at"), t, ["account_id", sa.text("created_at DESC")]
    )
    # The sweep (R18): unfinished uploads by age, and everything by creation for retention.
    op.create_index(
        f"ix_{t}_unfinished",
        t,
        ["created_at"],
        postgresql_where=sa.text("state NOT IN ('VERIFIED', 'REJECTED')"),
    )
    op.create_index(op.f(f"ix_{t}_created_at"), t, ["created_at"])
    _system_kinds(_SYSTEM_AFTER)


def downgrade() -> None:
    _system_kinds(_SYSTEM_BEFORE)
    op.drop_table("prescription_uploads")
