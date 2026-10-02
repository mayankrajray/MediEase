"""ChangeStaffRole — an owner changes a member's role (FR-ORG-04; spec R9, R11, AC5).

The first clinic mutation in the project, and deliberately the first one after
the audit log exists: the new role and the ``staff.role_changed`` event are
written in one transaction, so a role nobody can account for cannot happen
(R11, AC5).

The domain decides whether the change is allowed: ``ClinicMembership`` refuses
to demote the last active owner (R9 → ``CLN_LAST_OWNER``), and the caller
passes the clinic's current count of active owners. The membership is read
through the request's clinic scope, so another clinic's membership is not
found rather than refused (R8).

The member keeps their session: M1-P3 re-reads the membership on every
request, so the new role applies to their next request (FR-ORG-04).

Inviting and deactivating staff arrive in M1-P5.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.audit import record_clinic_event
from mediease_api.application.context import RequestContext
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.access import StaffMember
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "clinic_membership"


@dataclass(frozen=True, slots=True)
class ChangeStaffRoleCommand:
    membership_id: UUID
    role: Role


class ChangeStaffRole:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, cmd: ChangeStaffRoleCommand) -> StaffMember:
        with self._uow as uow:
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

            previous = membership.role
            if previous is cmd.role:
                # Nothing changed, so there is nothing to record (AC5 counts changes).
                return _staff_member(staff.list_staff(), cmd.membership_id)

            now = self._clock.now()
            membership.change_role(
                cmd.role, active_owner_count=staff.count_active_owners(), now=now
            )
            staff.update(membership)
            record_clinic_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.STAFF_ROLE_CHANGED,
                ctx=ctx,
                entity_type=ENTITY_TYPE,
                entity_id=membership.id,
                now=now,
                metadata={
                    "target_user_id": str(membership.user_id),
                    "from_role": previous.value,
                    "to_role": cmd.role.value,
                },
            )
            # The staff list is read before the commit: same transaction, and a
            # clinic has a handful of members, so no extra query shape is needed.
            updated = _staff_member(staff.list_staff(), cmd.membership_id)
            uow.commit()

        logger.info(
            "staff.role_changed",
            clinic_id=str(ctx.clinic_id),
            membership_id=str(cmd.membership_id),
            from_role=previous.value,
            to_role=cmd.role.value,
        )
        return updated


def _staff_member(staff: Sequence[StaffMember], membership_id: UUID) -> StaffMember:
    members = [m for m in staff if m.membership_id == membership_id]
    if not members:  # pragma: no cover - the row was just read in this transaction
        raise NotFound("membership")
    return members[0]
