"""Recording audit events from a use case (FR-AUD-01, spec R11).

Two helpers, because there are two kinds of actor in M1:

- ``record_user_event`` — something a user did to their own session (sign-in,
  sign-out). It belongs to the user, not to a clinic, so ``clinic_id`` is null.
- ``record_clinic_event`` — something a member did inside one clinic. The
  clinic, the actor and the request come from the ``RequestContext``, so a
  caller cannot accidentally attribute a change to the wrong clinic.

Both write through the unit of work they are given, so the row shares the
change's transaction. Which failures are audited is a deliberate choice:
anything an anonymous caller can trigger repeatedly is logged but not
recorded, so the table cannot be flooded (``domain/audit/actions.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from mediease_api.application.context import RequestContext, RequestInfo
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.identity.user import User
from mediease_api.ports.unit_of_work import UnitOfWork


def record_user_event(
    uow: UnitOfWork,
    *,
    event_id: UUID,
    action: AuditAction,
    user: User,
    info: RequestInfo,
    now: datetime,
    metadata: Mapping[str, str] | None = None,
) -> None:
    uow.audit.record(
        AuditEvent.record(
            id=event_id,
            action=action,
            actor_type=ActorType.OPS if user.is_platform_ops else ActorType.STAFF,
            actor_user_id=user.id,
            request_id=info.request_id,
            ip_hash=info.ip_hash,
            metadata=metadata,
            now=now,
        )
    )


def record_clinic_event(
    uow: UnitOfWork,
    *,
    event_id: UUID,
    action: AuditAction,
    ctx: RequestContext,
    entity_type: str,
    entity_id: UUID,
    now: datetime,
    metadata: Mapping[str, str] | None = None,
) -> None:
    uow.audit.record(
        AuditEvent.record(
            id=event_id,
            action=action,
            # Ops users cannot reach clinic routes (R10), so the actor is staff.
            actor_type=ActorType.STAFF,
            actor_user_id=ctx.user_id,
            clinic_id=ctx.clinic_id,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=ctx.request_id,
            ip_hash=ctx.ip_hash,
            metadata=metadata,
            now=now,
        )
    )
