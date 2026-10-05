"""The audit writer (``ports/audit.py``) over SQLAlchemy.

Inserts and flushes at once, inside the unit of work's transaction: a
constraint violation surfaces at the call that recorded the event, and the
change it describes rolls back with it (spec R11). There is no update or
delete method — the table refuses both anyway (FR-AUD-02).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from mediease_api.adapters.db.models import AuditEventRow
from mediease_api.domain.audit.event import AuditEvent


class SqlAlchemyAuditWriter:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, event: AuditEvent) -> None:
        self.record_many([event])

    def record_many(self, events: Sequence[AuditEvent]) -> None:
        # One flush: SQLAlchemy sends the rows as batched multi-row INSERTs.
        self._session.add_all([_row(event) for event in events])
        self._session.flush()


def _row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=event.id,
        clinic_id=event.clinic_id,
        actor_user_id=event.actor_user_id,
        actor_type=event.actor_type.value,
        action=event.action.value,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        request_id=event.request_id,
        ip_hash=event.ip_hash,
        event_metadata=dict(event.metadata),
        occurred_at=event.occurred_at,
    )
