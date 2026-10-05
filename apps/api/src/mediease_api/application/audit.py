"""Recording audit events from a use case (FR-AUD-01, spec R11).

One helper, because there is one shape: an ``Actor`` (who, with the request's
ID and IP fingerprint), an action, and optionally the clinic and the entity it
touched. The actor is built from the authenticated caller
(``application/context.py``), so a use case cannot attribute a change to
somebody else, and ops work is recorded as ``OPS`` without the caller
remembering to say so.

Events are written through the unit of work the caller is already in, so the
row shares the change's transaction. Which *failures* are audited is a
deliberate choice: anything an anonymous caller can trigger repeatedly is
logged but not recorded, so the table cannot be flooded
(``domain/audit/actions.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from mediease_api.application.context import Actor
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import AuditEvent
from mediease_api.ports.unit_of_work import UnitOfWork


def record_event(
    uow: UnitOfWork,
    *,
    event_id: UUID,
    action: AuditAction,
    actor: Actor,
    now: datetime,
    clinic_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    metadata: Mapping[str, str] | None = None,
) -> None:
    """Append one event. ``clinic_id`` is None for user-level actions (a sign-in)."""
    uow.audit.record(
        audit_event(
            event_id=event_id,
            action=action,
            actor=actor,
            now=now,
            clinic_id=clinic_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata,
        )
    )


def audit_event(
    *,
    event_id: UUID,
    action: AuditAction,
    actor: Actor,
    now: datetime,
    clinic_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    metadata: Mapping[str, str] | None = None,
) -> AuditEvent:
    """The event ``record_event`` would append, for callers that write many at once."""
    return AuditEvent.record(
        id=event_id,
        action=action,
        actor_type=actor.actor_type,
        actor_user_id=actor.user_id,
        clinic_id=clinic_id,
        entity_type=entity_type,
        entity_id=entity_id,
        request_id=actor.info.request_id,
        ip_hash=actor.info.ip_hash,
        metadata=metadata,
        now=now,
    )
