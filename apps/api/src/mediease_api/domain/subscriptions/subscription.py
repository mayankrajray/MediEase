"""A clinic's plan and trial (M6d-P7; FR-SUB-01; spec plans-and-trial; decisions B9, D4, D5).

Each clinic has one subscription (platform data, ``clinic_subscriptions``): a plan with its
limits, and a 14-day trial that starts when the clinic becomes ``ACTIVE``. The limits count
active doctor profiles and staff seats (invited or active memberships; the owner counts). Every
path that adds or brings back a doctor or a member checks them; nothing else is limited. When the
trial ends nothing is locked: the owner sees a banner and ops see a flag (D5).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.errors import DomainError
from mediease_api.domain.shared.time import require_utc

TRIAL_DAYS = 14


class Plan(StrEnum):
    SOLO = "SOLO"
    CLINIC = "CLINIC"
    PLUS = "PLUS"


class Limit(StrEnum):
    DOCTORS = "doctors"
    USERS = "users"


@dataclass(frozen=True, slots=True)
class PlanLimits:
    doctors: int
    users: int | None  # None: no limit

    def allowed(self, limit: Limit) -> int | None:
        return self.doctors if limit is Limit.DOCTORS else self.users


# D4: Solo is one doctor and two people (the owner counts); Clinic three and five; Plus five and
# no limit on people.
LIMITS: dict[Plan, PlanLimits] = {
    Plan.SOLO: PlanLimits(doctors=1, users=2),
    Plan.CLINIC: PlanLimits(doctors=3, users=5),
    Plan.PLUS: PlanLimits(doctors=5, users=None),
}

PLAN_NAMES: dict[Plan, str] = {Plan.SOLO: "Solo", Plan.CLINIC: "Clinic", Plan.PLUS: "Clinic Plus"}


class PlanLimitReached(DomainError):
    """R4: adding this doctor or person would pass the plan's limit."""

    code = "SUB_LIMIT_REACHED"

    def __init__(self, plan: Plan, limit: Limit, allowed: int) -> None:
        what = "doctor" if limit is Limit.DOCTORS else "staff member"
        super().__init__(
            f"The {PLAN_NAMES[plan]} plan allows {allowed} {what}{'s' if allowed != 1 else ''}."
            " Ask MediEase to change the plan.",
            plan=plan.value,
            limit=limit.value,
            allowed=str(allowed),
        )
        self.plan = plan
        self.limit = limit


class PlanTooSmall(DomainError):
    """R8: the clinic already has more doctors or people than the plan allows."""

    code = "SUB_PLAN_TOO_SMALL"

    def __init__(self, plan: Plan, limit: Limit, allowed: int, used: int) -> None:
        super().__init__(
            f"The clinic has {used} {limit.value}; the {PLAN_NAMES[plan]} plan allows {allowed}.",
            plan=plan.value,
            limit=limit.value,
            allowed=str(allowed),
            used=str(used),
        )


@dataclass(frozen=True, slots=True)
class Usage:
    doctors: int
    users: int

    def of(self, limit: Limit) -> int:
        return self.doctors if limit is Limit.DOCTORS else self.users


class TrialState(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    NONE = "NONE"  # a clinic from before plans (migration 0041) has no trial


@dataclass(frozen=True, slots=True)
class Subscription:
    clinic_id: UUID
    plan: Plan
    trial_started_at: datetime | None
    trial_ends_at: datetime | None
    created_at: datetime
    updated_at: datetime
    plan_changed_at: datetime | None = None
    plan_changed_by: UUID | None = None
    # False only for the clinics that existed before plans (no trial is owed to them).
    has_trial: bool = True

    @classmethod
    def start(cls, *, clinic_id: UUID, plan: Plan, now: datetime) -> Subscription:
        """R1: a new clinic's subscription; its trial waits for the clinic to become active."""
        now = require_utc(now, "now")
        return cls(clinic_id, plan, None, None, now, now)

    @classmethod
    def legacy(cls, clinic_id: UUID, now: datetime) -> Subscription:
        """R2: what a clinic without a row has, as migration 0041 gives them: Plus, no trial."""
        return cls(clinic_id, Plan.PLUS, None, None, now, now, has_trial=False)

    @property
    def limits(self) -> PlanLimits:
        return LIMITS[self.plan]

    def start_trial(self, now: datetime) -> Subscription:
        """R3: 14 days from the clinic's first activation; never restarted."""
        if not self.has_trial or self.trial_started_at is not None:
            return self
        now = require_utc(now, "now")
        return replace(
            self,
            trial_started_at=now,
            trial_ends_at=now + timedelta(days=TRIAL_DAYS),
            updated_at=now,
        )

    def trial_state(self, now: datetime) -> TrialState:
        if not self.has_trial:
            return TrialState.NONE
        if self.trial_ends_at is None:
            return TrialState.NOT_STARTED
        return TrialState.ACTIVE if now < self.trial_ends_at else TrialState.ENDED

    def days_left(self, now: datetime) -> int | None:
        """Whole days left in the trial, rounded up (0 once it has ended)."""
        if self.trial_ends_at is None:
            return None
        seconds = (self.trial_ends_at - now).total_seconds()
        return max(0, -(-int(seconds) // 86_400))

    def require_room(self, limit: Limit, used: int, adding: int) -> None:
        """R4: ``used + adding`` must stay within the plan (``adding`` 0 re-checks a seat)."""
        allowed = self.limits.allowed(limit)
        if allowed is not None and used + adding > allowed:
            raise PlanLimitReached(self.plan, limit, allowed)

    def change_plan(self, plan: Plan, *, usage: Usage, by: UUID, now: datetime) -> Subscription:
        """R8: ops choose the plan; never one smaller than what the clinic already uses."""
        if plan is self.plan:
            return self
        for limit in Limit:
            allowed = LIMITS[plan].allowed(limit)
            if allowed is not None and usage.of(limit) > allowed:
                raise PlanTooSmall(plan, limit, allowed, usage.of(limit))
        now = require_utc(now, "now")
        return replace(self, plan=plan, plan_changed_at=now, plan_changed_by=by, updated_at=now)


def plan_for_application(*, solo: bool, doctors: int) -> Plan:
    """R1: an approved application's plan: Solo for a solo doctor, else the smallest that fits."""
    if solo and doctors <= LIMITS[Plan.SOLO].doctors:
        return Plan.SOLO
    return Plan.CLINIC if doctors <= LIMITS[Plan.CLINIC].doctors else Plan.PLUS
