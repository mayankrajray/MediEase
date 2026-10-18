"""Background jobs (M5-P1, migration 0014, ADR-0005, docs/ARCHITECTURE.md §7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mediease_api.adapters.db.models.base import Base, Keyed, Timestamps, enum_check
from mediease_api.domain.jobs.job import (
    DEDUPE_STATES,
    MAX_ATTEMPTS_LIMIT,
    SYSTEM_KINDS,
    JobState,
)

_SYSTEM_KIND_LIST = ", ".join(f"'{kind}'" for kind in sorted(SYSTEM_KINDS))
_DEDUPE_STATE_LIST = ", ".join(f"'{state.value}'" for state in DEDUPE_STATES)


class JobRow(Keyed, Timestamps, Base):
    """A unit of background work.

    Deliberately not a ``TenantOwned`` table: ``clinic_id`` is null for the system kinds the CHECK
    lists, so no tenant repository can own it. It is reached only through the job queue and the
    worker's store, which scope by clinic where the job has one (tests/tenancy).
    """

    __tablename__ = "jobs"
    __table_args__ = (
        enum_check("state", JobState),
        CheckConstraint("kind ~ '^[a-z][a-z0-9_]{2,63}$'", name="kind_format"),
        CheckConstraint(
            f"attempts >= 0 AND max_attempts BETWEEN 1 AND {MAX_ATTEMPTS_LIMIT}"
            " AND attempts <= max_attempts",
            name="attempts_range",
        ),
        # A running job has a holder and a lock time, and only a running job does.
        CheckConstraint(
            "(state = 'running') = (locked_by IS NOT NULL AND locked_at IS NOT NULL)",
            name="lock_when_running",
        ),
        # R9d: no clinic if and only if the kind is a system kind.
        CheckConstraint(
            f"(clinic_id IS NULL) = (kind IN ({_SYSTEM_KIND_LIST}))", name="system_kind"
        ),
        # What the worker asks: due queued jobs, oldest first.
        Index("ix_jobs_claim", "run_at", postgresql_where=text("state = 'queued'")),
        # What the reaper asks: running jobs by lock age.
        Index("ix_jobs_running", "locked_at", postgresql_where=text("state = 'running'")),
        Index("ix_jobs_clinic_id", "clinic_id"),
        # R9c: a cancelled or dead job never blocks the same logical key later.
        Index(
            "uq_jobs_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text(f"state IN ({_DEDUPE_STATE_LIST})"),
        ),
    )

    clinic_id: Mapped[UUID | None] = mapped_column(ForeignKey("clinics.id"))
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(Text)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("5"))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
