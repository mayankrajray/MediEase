"""append-only audit_events and the v_clinic_activity support view (M1-P4)

FR-AUD-01, FR-AUD-02, FR-OPS-04; docs/DATA_MODEL.md "M1". Expand-only: one new
table and one view, so M1-P3 code keeps working against this schema.

Immutability (FR-AUD-02, AC6) is enforced by two triggers that raise, not by
``REVOKE``: the application connects as the role that owns the schema, and an
owner can grant its own privileges back, so a revoke would not be a boundary.
The triggers refuse ``UPDATE``, ``DELETE`` and ``TRUNCATE`` for every
non-superuser role, including ours. A deliberate correction (a data migration)
has to disable them explicitly, which is exactly the visibility we want
(docs/RUNBOOK.md).

``clinic_id`` is nullable: a sign-in belongs to a user, not to a clinic, so
clinic activity is derived by joining the actor's memberships.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'AUD_APPEND_ONLY: audit_events is append-only (FR-AUD-02); % is not allowed',
        TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$
"""

# Row-level for UPDATE/DELETE, statement-level for TRUNCATE: PostgreSQL does
# not allow one trigger to cover both.
_APPEND_ONLY_TRIGGERS = (
    """
    CREATE TRIGGER trg_audit_events_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()
    """,
    """
    CREATE TRIGGER trg_audit_events_no_truncate
    BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only()
    """,
)

# Support view (FR-OPS-04): "is this clinic being used, and by whom?" with no
# clinical column and no patient data. Read by the ops console from M6-P4.
_CLINIC_ACTIVITY_VIEW = """
CREATE VIEW v_clinic_activity AS
SELECT
    c.id    AS clinic_id,
    c.name  AS clinic_name,
    c.status,
    staff.active_owners,
    staff.active_doctors,
    staff.active_front_desk,
    staff.last_sign_in_at,
    events.audit_events_7d,
    events.audit_events_30d,
    events.last_event_at
FROM clinics c
LEFT JOIN LATERAL (
    SELECT
        count(*) FILTER (WHERE m.role = 'OWNER')      AS active_owners,
        count(*) FILTER (WHERE m.role = 'DOCTOR')     AS active_doctors,
        count(*) FILTER (WHERE m.role = 'FRONT_DESK') AS active_front_desk,
        max(u.last_login_at)                          AS last_sign_in_at
    FROM clinic_memberships m
    JOIN users u ON u.id = m.user_id
    WHERE m.clinic_id = c.id AND m.status = 'ACTIVE'
) staff ON true
LEFT JOIN LATERAL (
    SELECT
        count(*) FILTER (WHERE e.occurred_at >= now() - interval '7 days')  AS audit_events_7d,
        count(*) FILTER (WHERE e.occurred_at >= now() - interval '30 days') AS audit_events_30d,
        max(e.occurred_at)                                                  AS last_event_at
    FROM audit_events e
    WHERE e.clinic_id = c.id
) events ON true
"""


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('STAFF', 'OPS', 'PATIENT_LINK', 'SYSTEM')",
            name=op.f("ck_audit_events_actor_type"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_audit_events_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_audit_events_actor_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_clinic_id_occurred_at", "audit_events", ["clinic_id", "occurred_at"]
    )
    op.create_index(
        "ix_audit_events_actor_user_id_occurred_at",
        "audit_events",
        ["actor_user_id", "occurred_at"],
    )

    op.execute(_APPEND_ONLY_FUNCTION)
    for trigger in _APPEND_ONLY_TRIGGERS:
        op.execute(trigger)

    op.execute(_CLINIC_ACTIVITY_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_clinic_activity")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_truncate ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update_delete ON audit_events")
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")
