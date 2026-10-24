"""Audit port: where a recorded action goes (FR-AUD-01, spec R11).

The writer is obtained from the unit of work (``uow.audit``), so the row lands
in the same transaction as the change it describes: commit both, or neither.
Nothing anywhere may change an entry (FR-AUD-02). From M6a-P8 an owner reads their clinic's log
(FR-AUD-03) through `AuditReader`, reached only as `uow.tenant(clinic).audit_log`: bound to one
clinic like a tenant repository, with no way to name another.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.audit.event import ActorType, AuditEvent


class AuditWriter(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Append the event. Fails loudly: an unaudited change must not commit."""
        ...

    def record_many(self, events: Sequence[AuditEvent]) -> None:
        """Append several events in one round trip (the ops import, M2-P4). Same guarantees."""
        ...


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One audit event as the owner's log shows it (M6a-P8).

    ``actor_name`` and ``actor_role`` are the member's current name and role in this clinic (None
    for ops, the system, a patient, or somebody no longer a member); ``patient_code`` is set when
    the record is one of this clinic's patients. The IP hash is never read.
    """

    id: UUID
    occurred_at: datetime
    action: str
    actor_type: ActorType
    actor_user_id: UUID | None
    actor_name: str | None
    actor_role: str | None
    entity_type: str | None
    entity_id: UUID | None
    patient_code: str | None
    metadata: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AuditCursor:
    """Keyset position: entries strictly older than this one."""

    occurred_at: datetime
    id: UUID


class AuditReader(Protocol):
    """One clinic's audit log, newest first (FR-AUD-03). Read-only."""

    def list(
        self,
        *,
        since: datetime,
        until: datetime,
        actions: Collection[str] | None,
        actor_user_id: UUID | None,
        after: AuditCursor | None,
        limit: int,
    ) -> Sequence[AuditEntry]:
        """Entries with ``since <= occurred_at < until``; ``actions`` None means every action."""
        ...
