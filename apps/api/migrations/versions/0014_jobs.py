"""background jobs and their health view (M5-P1)

NFR-13; spec reminders-and-messaging R9-R11, R9a-R9e; ADR-0005; docs/ARCHITECTURE.md §7.
Expand-only.

``jobs``: one row per unit of background work. ``clinic_id`` is null exactly for the system kinds
in ``ck_jobs_system_kind`` (adding a kind is a migration that replaces that CHECK).
``uq_jobs_dedupe_key`` is unique only among queued, running and succeeded jobs, so a cancelled or
dead job never blocks the same logical key later. ``ix_jobs_claim`` and ``ix_jobs_running`` are
partial: the worker and the reaper each read a small slice of a table that otherwise only grows.
``v_job_health`` is a support view with counts and ages by kind; it holds no clinic or patient data.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.SmallInteger(), server_default=sa.text("5"), nullable=False),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('queued', 'running', 'succeeded', 'dead', 'cancelled')",
            name=op.f("ck_jobs_state"),
        ),
        sa.CheckConstraint("kind ~ '^[a-z][a-z0-9_]{2,63}$'", name=op.f("ck_jobs_kind_format")),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts BETWEEN 1 AND 20 AND attempts <= max_attempts",
            name=op.f("ck_jobs_attempts_range"),
        ),
        sa.CheckConstraint(
            "(state = 'running') = (locked_by IS NOT NULL AND locked_at IS NOT NULL)",
            name=op.f("ck_jobs_lock_when_running"),
        ),
        sa.CheckConstraint(
            "(clinic_id IS NULL) = (kind IN ('purge_expired_auth_and_links'))",
            name=op.f("ck_jobs_system_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_jobs_clinic_id_clinics")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(
        "ix_jobs_claim", "jobs", ["run_at"], postgresql_where=sa.text("state = 'queued'")
    )
    op.create_index(
        "ix_jobs_running", "jobs", ["locked_at"], postgresql_where=sa.text("state = 'running'")
    )
    op.create_index("ix_jobs_clinic_id", "jobs", ["clinic_id"])
    op.create_index(
        "uq_jobs_dedupe_key",
        "jobs",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('queued', 'running', 'succeeded')"),
    )
    op.execute(
        """
        CREATE VIEW v_job_health AS
        SELECT kind,
               count(*) FILTER (WHERE state = 'queued' AND run_at <= now()) AS due,
               count(*) FILTER (WHERE state = 'queued' AND run_at > now()) AS scheduled,
               count(*) FILTER (WHERE state = 'running') AS running,
               count(*) FILTER (
                   WHERE state = 'running' AND locked_at < now() - interval '5 minutes'
               ) AS stale,
               count(*) FILTER (WHERE state = 'dead') AS dead,
               count(*) FILTER (
                   WHERE state = 'dead' AND finished_at > now() - interval '24 hours'
               ) AS dead_24h,
               floor(extract(epoch FROM now() - min(run_at) FILTER (
                   WHERE state = 'queued' AND run_at <= now()
               )))::bigint AS oldest_due_age_seconds
        FROM jobs
        GROUP BY kind
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_job_health")
    op.drop_table("jobs")
