"""ops roles and the review of clinic applications (M6c-P2)

Spec clinic-onboarding R24-R40; milestone decision M3. Expand-only.

- ``users.ops_roles`` (``OPS_ADMIN``, ``OPS_REVIEWER``); every existing ops user gets both.
- ``clinic_applications``: who took it, who decided, when, the rejection reason and message, and
  (P3) the clinic an approval created.
- ``clinic_application_checks``: one reviewer check per application doctor.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS = (
    "'REGISTRATION_NOT_FOUND', 'CERTIFICATE_UNCLEAR', 'DETAILS_DO_NOT_MATCH', 'NOT_ELIGIBLE',"
    " 'DUPLICATE', 'OTHER'"
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "ops_roles",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE users SET ops_roles = ARRAY['OPS_ADMIN', 'OPS_REVIEWER'] WHERE is_platform_ops"
    )

    a = "clinic_applications"
    for name in ("taken_by", "decided_by"):
        op.add_column(a, sa.Column(name, sa.Uuid(), nullable=True))
        op.create_foreign_key(op.f(f"fk_{a}_{name}_users"), a, "users", [name], ["id"])
    op.add_column(a, sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(a, sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(a, sa.Column("decision_reason", sa.Text(), nullable=True))
    op.add_column(a, sa.Column("decision_message", sa.Text(), nullable=True))
    # Not ``clinic_id``: an application is platform data, never a tenant row (ADR-0020).
    op.add_column(a, sa.Column("created_clinic_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f(f"fk_{a}_created_clinic_id_clinics"), a, "clinics", ["created_clinic_id"], ["id"]
    )
    op.create_check_constraint(
        op.f(f"ck_{a}_decision_reason"), a, f"decision_reason IN ({_REASONS})"
    )
    op.create_check_constraint(
        op.f(f"ck_{a}_decided"),
        a,
        "(status IN ('APPROVED', 'REJECTED')) = (decided_at IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f(f"ck_{a}_rejected_reason"), a, "(status = 'REJECTED') = (decision_reason IS NOT NULL)"
    )

    c = "clinic_application_checks"
    op.create_table(
        c,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("checked_by", sa.Uuid(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("register_checked", sa.Boolean(), nullable=False),
        sa.Column("certificate_matches", sa.Boolean(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("result IN ('VERIFIED', 'NOT_VERIFIED')", name=op.f(f"ck_{c}_result")),
        sa.CheckConstraint(
            "result = 'NOT_VERIFIED' OR (register_checked AND certificate_matches)",
            name=op.f(f"ck_{c}_verified_needs_both"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["clinic_applications.id"],
            name=op.f(f"fk_{c}_application_id_clinic_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"],
            ["clinic_application_doctors.id"],
            name=op.f(f"fk_{c}_doctor_id_clinic_application_doctors"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["checked_by"], ["users.id"], name=op.f(f"fk_{c}_checked_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{c}")),
        sa.UniqueConstraint("doctor_id", name=op.f(f"uq_{c}_doctor_id")),
    )


def downgrade() -> None:
    op.drop_table("clinic_application_checks")
    a = "clinic_applications"
    for name in ("rejected_reason", "decided", "decision_reason"):
        op.drop_constraint(op.f(f"ck_{a}_{name}"), a, type_="check")
    op.drop_constraint(op.f(f"fk_{a}_created_clinic_id_clinics"), a, type_="foreignkey")
    for name in ("taken_by", "decided_by"):
        op.drop_constraint(op.f(f"fk_{a}_{name}_users"), a, type_="foreignkey")
    for name in (
        "created_clinic_id",
        "decision_message",
        "decision_reason",
        "decided_at",
        "taken_at",
        "decided_by",
        "taken_by",
    ):
        op.drop_column(a, name)
    op.drop_column("users", "ops_roles")
