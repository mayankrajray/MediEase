"""Plans, the trial and their limits (M6d-P7; FR-SUB-01; spec plans-and-trial; B9, D4, D5).

``require_room`` is the one limit check. It locks the clinic's subscription row, so two invites
or doctors racing for the last place serialise, and it is called inside the transaction of every
path that adds or brings back a doctor or a member: ``AddDoctor.in_transaction`` and doctor
reactivation (``UpdateDoctor``), ``InviteStaff.in_transaction`` (a new or returning member) and
``AcceptInvite``. Approval and the ops wizard go through those, so they are limited too.

Seats are invited or active memberships (an invitation holds its place); doctors are active
profiles. A clinic without a row (created before migration 0041 and not backfilled, or written
straight to the database by a test) is treated as Plus without a trial, as the migration made
every existing clinic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.membership import MembershipStatus
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.subscriptions.subscription import (
    Limit,
    Plan,
    PlanLimitReached,
    Subscription,
    TrialState,
    Usage,
)
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY = "clinic"
_SEATS = (MembershipStatus.INVITED, MembershipStatus.ACTIVE)


def load_subscription(
    uow: UnitOfWork, clinic_id: UUID, now: datetime, *, for_update: bool = False
) -> Subscription:
    found = uow.subscriptions.get(clinic_id, for_update=for_update)
    if found is not None:
        return found
    if for_update:
        # No row to lock: the clinic row serialises the checks instead.
        uow.clinics.get(clinic_id, for_update=True)
    return Subscription.legacy(clinic_id, now)


def usage(tenant: TenantRepositories) -> Usage:
    return Usage(
        doctors=sum(1 for d in tenant.doctors.list() if d.is_active),
        users=sum(1 for m in tenant.memberships.list() if m.status in _SEATS),
    )


def require_room(
    uow: UnitOfWork, clinic_id: UUID, limit: Limit, *, adding: int, now: datetime
) -> None:
    """R4: ``SUB_LIMIT_REACHED`` unless the clinic has room for ``adding`` more."""
    subscription = load_subscription(uow, clinic_id, now, for_update=True)
    used = usage(uow.tenant(clinic_id)).of(limit)
    try:
        subscription.require_room(limit, used, adding)
    except PlanLimitReached:
        logger.info(
            "subscription.limit_reached",
            clinic_id=str(clinic_id),
            plan=subscription.plan.value,
            limit=limit.value,
            used=used,
        )
        raise


def open_subscription(uow: UnitOfWork, clinic_id: UUID, plan: Plan, now: datetime) -> None:
    """R1: a new clinic's row, in the transaction that creates the clinic."""
    uow.subscriptions.add(Subscription.start(clinic_id=clinic_id, plan=plan, now=now))


def start_trial(uow: UnitOfWork, clinic_id: UUID, now: datetime) -> None:
    """R3: the clinic became active for the first time; its 14 days begin."""
    subscription = uow.subscriptions.get(clinic_id, for_update=True)
    if subscription is None:
        return  # a clinic from before plans has no trial (R2)
    started = subscription.start_trial(now)
    if started is not subscription:
        uow.subscriptions.update(started)
        logger.info("subscription.trial_started", clinic_id=str(clinic_id))


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    subscription: Subscription
    usage: Usage
    now: datetime

    @property
    def trial(self) -> TrialState:
        return self.subscription.trial_state(self.now)

    @property
    def days_left(self) -> int | None:
        return self.subscription.days_left(self.now)


class GetSubscription:
    """R6: the owner's plan, its limits, what the clinic uses and the trial's days left."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext) -> SubscriptionView:
        now = self._clock.now()
        with self._uow as uow:
            subscription = load_subscription(uow, ctx.clinic_id, now)
            used = usage(uow.tenant(ctx.clinic_id))
        return SubscriptionView(subscription, used, now)


class SetPlan:
    """R8: ops choose a clinic's plan (never one smaller than its use); audited."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, actor: Actor, clinic_id: UUID, plan: Plan) -> SubscriptionView:
        with self._uow as uow:
            now = self._clock.now()
            if uow.clinics.get(clinic_id) is None:
                raise NotFound("clinic")
            current = uow.subscriptions.get(clinic_id, for_update=True)
            if current is None:
                current = Subscription.legacy(clinic_id, now)
                uow.subscriptions.add(current)
            used = usage(uow.tenant(clinic_id))
            changed = current.change_plan(plan, usage=used, by=actor.user_id, now=now)
            if changed is not current:
                uow.subscriptions.update(changed)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.SUBSCRIPTION_PLAN_CHANGED,
                    actor=actor,
                    now=now,
                    clinic_id=clinic_id,
                    entity_type=ENTITY,
                    entity_id=clinic_id,
                    metadata={"from": current.plan.value, "to": plan.value},
                )
            uow.commit()
        logger.info("subscription.plan_set", clinic_id=str(clinic_id), plan=plan.value)
        return SubscriptionView(changed, used, now)
