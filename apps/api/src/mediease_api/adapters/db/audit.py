"""The audit writer and, from M6a-P8, the owner's reader (``ports/audit.py``) over SQLAlchemy.

Inserts and flushes at once, inside the unit of work's transaction: a
constraint violation surfaces at the call that recorded the event, and the
change it describes rolls back with it (spec R11). There is no update or
delete method — the table refuses both anyway (FR-AUD-02).
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models import (
    AuditEventRow,
    ClinicMembershipRow,
    PatientRow,
    UserRow,
)
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.ports.audit import AuditCursor, AuditEntry


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


class SqlAlchemyAuditReader:
    """One clinic's audit log (M6a-P8, FR-AUD-03; reviewed tenancy exception).

    ``audit_events`` has no tenant repository (its ``clinic_id`` is nullable and it is append
    only), so this reader carries the scope itself: it is constructed with one clinic, and its one
    query filters the events, the memberships and the patients it joins by that clinic. Tested in
    ``tests/tenancy/``.
    """

    def __init__(self, session: Session, clinic_id: UUID) -> None:
        self._session = session
        self._clinic_id = clinic_id

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
        e = AuditEventRow
        query = (
            select(e, UserRow.full_name, ClinicMembershipRow.role, PatientRow.code)
            .outerjoin(UserRow, UserRow.id == e.actor_user_id)
            .outerjoin(
                ClinicMembershipRow,
                and_(
                    ClinicMembershipRow.clinic_id == self._clinic_id,
                    ClinicMembershipRow.user_id == e.actor_user_id,
                ),
            )
            .outerjoin(
                PatientRow,
                and_(
                    e.entity_type == "patient",
                    PatientRow.clinic_id == self._clinic_id,
                    PatientRow.id == e.entity_id,
                ),
            )
            .where(e.clinic_id == self._clinic_id, e.occurred_at >= since, e.occurred_at < until)
            .order_by(e.occurred_at.desc(), e.id.desc())
            .limit(limit)
        )
        if actions is not None:
            query = query.where(e.action.in_(sorted(actions)))
        if actor_user_id is not None:
            query = query.where(e.actor_user_id == actor_user_id)
        if after is not None:
            query = query.where(
                or_(
                    e.occurred_at < after.occurred_at,
                    and_(e.occurred_at == after.occurred_at, e.id < after.id),
                )
            )
        entries = []
        for row, full_name, role, code in self._session.execute(query):
            member = role is not None and ActorType(row.actor_type) is ActorType.STAFF
            entries.append(
                AuditEntry(
                    id=row.id,
                    occurred_at=row.occurred_at.astimezone(UTC),
                    action=row.action,
                    actor_type=ActorType(row.actor_type),
                    actor_user_id=row.actor_user_id,
                    actor_name=full_name if member else None,
                    actor_role=role if member else None,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    patient_code=code,
                    metadata=dict(row.event_metadata),
                )
            )
        return entries
