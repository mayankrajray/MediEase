"""DeactivateStaff — take a member's access away (FR-ORG-04; spec R7, R9, R11).

The counterpart to the role change in M1-P4, and deliberately the same shape:
read through the request's clinic scope, let the domain decide (the last
active owner cannot be removed, R9), write the change and its
``staff.deactivated`` event in one transaction.

There is no way back in M1: the membership lifecycle is
``INVITED → ACTIVE → DEACTIVATED`` (spec §3), so a clinic that deactivated
somebody by mistake invites them again, and the audit trail shows both steps.

Effect is immediate in practice: M1-P3 re-reads the membership on every
request, so the member's next call is refused with ``AUTH_ACCOUNT_DISABLED``
(AC4) even though their access token has not expired.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "clinic_membership"


@dataclass(frozen=True, slots=True)
class DeactivateStaffCommand:
    membership_id: UUID


class DeactivateStaff:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, cmd: DeactivateStaffCommand) -> StaffMember:
        with self._uow as uow:
            now = self._clock.now()
            staff = uow.tenant(ctx.clinic_id).memberships
            membership = staff.get(cmd.membership_id)
            if membership is None:
                logger.info(
                    "tenancy.not_found",
                    entity="membership",
                    entity_id=str(cmd.membership_id),
                    clinic_id=str(ctx.clinic_id),
                )
                raise NotFound("membership")

            previous = membership.status
            membership.deactivate(active_owner_count=staff.count_active_owners(), now=now)
            staff.update(membership)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.STAFF_DEACTIVATED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=membership.id,
                metadata={
                    "target_user_id": str(membership.user_id),
                    "role": membership.role.value,
                    "from_status": previous.value,
                },
            )
            member = next(m for m in staff.list_staff() if m.membership_id == cmd.membership_id)
            uow.commit()

        logger.info(
            "staff.deactivated",
            clinic_id=str(ctx.clinic_id),
            membership_id=str(cmd.membership_id),
        )
        return member
