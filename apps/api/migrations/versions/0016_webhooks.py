"""provider webhooks, status fields and two system job kinds (M5-P3)

FR-MSG-03; spec reminders-and-messaging R12, R13, R15; M5-P3 decisions 2A, 3A. Expand-only.

``webhook_events``: one row per webhook body (``event_key`` is its SHA-256, unique, so Meta's
redeliveries are stored once), redacted to statuses and IDs, processed by a job and purged after
7 days. ``messages.pricing_category`` keeps the provider's category for P5's cost ledger.
``ck_jobs_system_kind`` gains ``process_webhook_event`` and ``reconcile_messages``.
``v_message_health`` gains ``unconfirmed_24h``: messages still ``SENT`` a day after sending.
``ck_messages_sent_has_provider_id`` becomes one-way: a message the provider accepted and later
reported ``failed`` keeps its provider ID and send time.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_KINDS = "'purge_expired_auth_and_links'"
_NEW_KINDS = "'process_webhook_event', 'purge_expired_auth_and_links', 'reconcile_messages'"

_VIEW = """
CREATE OR REPLACE VIEW v_message_health AS
SELECT channel,
       template_key,
       status,
       count(*) AS total,
       count(*) FILTER (WHERE created_at > now() - interval '24 hours') AS last_24h,
       count(*) FILTER (WHERE error_code = 'MSG_OUTCOME_UNKNOWN') AS outcome_unknown,
       floor(extract(epoch FROM now() - min(created_at) FILTER (
           WHERE status = 'QUEUED'
       )))::bigint AS oldest_queued_age_seconds{extra}
FROM messages
GROUP BY channel, template_key, status
"""
_UNCONFIRMED = """,
       count(*) FILTER (
           WHERE status = 'SENT' AND sent_at < now() - interval '24 hours'
       ) AS unconfirmed_24h"""


def _system_kinds(kinds: str) -> None:
    op.drop_constraint(op.f("ck_jobs_system_kind"), "jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_jobs_system_kind"), "jobs", f"(clinic_id IS NULL) = (kind IN ({kinds}))"
    )


_SENT_BOTH_WAYS = (
    "(status IN ('SENT', 'DELIVERED', 'READ'))"
    " = (sent_at IS NOT NULL AND provider_message_id IS NOT NULL)"
)
_SENT_ONE_WAY = (
    "status NOT IN ('SENT', 'DELIVERED', 'READ')"
    " OR (sent_at IS NOT NULL AND provider_message_id IS NOT NULL)"
)


def _sent_check(condition: str) -> None:
    op.drop_constraint(op.f("ck_messages_sent_has_provider_id"), "messages", type_="check")
    op.create_check_constraint(op.f("ck_messages_sent_has_provider_id"), "messages", condition)


def upgrade() -> None:
    op.add_column("messages", sa.Column("pricing_category", sa.Text(), nullable=True))
    _sent_check(_SENT_ONE_WAY)
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("event_key", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint("event_key", name=op.f("uq_webhook_events_event_key")),
    )
    op.create_index(
        "ix_webhook_events_received_at_unprocessed",
        "webhook_events",
        ["received_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.create_index("ix_webhook_events_received_at", "webhook_events", ["received_at"])
    _system_kinds(_NEW_KINDS)
    op.execute(_VIEW.format(extra=_UNCONFIRMED))


def downgrade() -> None:
    # A view cannot drop a column in place.
    op.execute("DROP VIEW IF EXISTS v_message_health")
    op.execute(_VIEW.format(extra=""))
    op.execute(f"DELETE FROM jobs WHERE kind IN ({_NEW_KINDS}) AND kind NOT IN ({_OLD_KINDS})")
    _system_kinds(_OLD_KINDS)
    op.drop_table("webhook_events")
    # Rows failed after acceptance would break the stricter check: clear what it forbids.
    op.execute(
        "UPDATE messages SET sent_at = NULL, provider_message_id = NULL"
        " WHERE status IN ('QUEUED', 'FAILED')"
    )
    _sent_check(_SENT_BOTH_WAYS)
    op.drop_column("messages", "pricing_category")
