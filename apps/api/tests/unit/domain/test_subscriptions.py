"""Plans, the trial and limits (M6d-P7; FR-SUB-01; spec plans-and-trial)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from mediease_api.domain.subscriptions.subscription import (
    LIMITS,
    Limit,
    Plan,
    PlanLimitReached,
    PlanTooSmall,
    Subscription,
    TrialState,
    Usage,
    plan_for_application,
)
from tests.builders import NOW, new_id


def _new(plan: Plan = Plan.SOLO) -> Subscription:
    return Subscription.start(clinic_id=new_id(), plan=plan, now=NOW)


def test_fr_sub_01_d4_the_plans_and_their_limits() -> None:
    assert {p: (LIMITS[p].doctors, LIMITS[p].users) for p in Plan} == {
        Plan.SOLO: (1, 2),
        Plan.CLINIC: (3, 5),
        Plan.PLUS: (5, None),
    }


def test_r3_the_trial_starts_once_and_lasts_14_days() -> None:
    subscription = _new()
    assert subscription.trial_state(NOW) is TrialState.NOT_STARTED
    assert subscription.days_left(NOW) is None

    started = subscription.start_trial(NOW)
    assert started.trial_ends_at == NOW + timedelta(days=14)
    assert started.start_trial(NOW + timedelta(days=3)) is started  # never restarted
    assert started.trial_state(NOW + timedelta(days=13, hours=23)) is TrialState.ACTIVE
    assert started.days_left(NOW) == 14
    assert started.days_left(NOW + timedelta(days=13, hours=1)) == 1
    assert started.trial_state(NOW + timedelta(days=14)) is TrialState.ENDED
    assert started.days_left(NOW + timedelta(days=20)) == 0


def test_r2_a_clinic_from_before_plans_is_plus_with_no_trial() -> None:
    legacy = Subscription.legacy(new_id(), NOW)
    assert legacy.plan is Plan.PLUS and legacy.trial_state(NOW) is TrialState.NONE
    assert legacy.start_trial(NOW) is legacy


@pytest.mark.parametrize(
    ("plan", "limit", "used", "adding", "fits"),
    [
        (Plan.SOLO, Limit.DOCTORS, 0, 1, True),
        (Plan.SOLO, Limit.DOCTORS, 1, 1, False),
        (Plan.SOLO, Limit.USERS, 1, 1, True),
        (Plan.SOLO, Limit.USERS, 2, 1, False),
        (Plan.SOLO, Limit.USERS, 2, 0, True),
        (Plan.SOLO, Limit.USERS, 3, 0, False),
        (Plan.CLINIC, Limit.DOCTORS, 2, 1, True),
        (Plan.CLINIC, Limit.USERS, 5, 1, False),
        (Plan.PLUS, Limit.DOCTORS, 5, 1, False),
        (Plan.PLUS, Limit.USERS, 500, 1, True),
    ],
)
def test_r4_room_on_the_plan(plan: Plan, limit: Limit, used: int, adding: int, fits: bool) -> None:
    subscription = _new(plan)
    if fits:
        subscription.require_room(limit, used, adding)
        return
    with pytest.raises(PlanLimitReached) as raised:
        subscription.require_room(limit, used, adding)
    allowed = LIMITS[plan].allowed(limit)
    assert raised.value.details == {
        "plan": plan.value,
        "limit": limit.value,
        "allowed": str(allowed),
    }


def test_r8_a_plan_is_never_smaller_than_what_the_clinic_uses() -> None:
    subscription = _new(Plan.PLUS)
    by = new_id()
    with pytest.raises(PlanTooSmall) as raised:
        subscription.change_plan(Plan.SOLO, usage=Usage(doctors=1, users=3), by=by, now=NOW)
    assert raised.value.details == {"plan": "SOLO", "limit": "users", "allowed": "2", "used": "3"}

    changed = subscription.change_plan(Plan.CLINIC, usage=Usage(3, 5), by=by, now=NOW)
    assert (changed.plan, changed.plan_changed_by, changed.plan_changed_at) == (
        Plan.CLINIC,
        by,
        NOW,
    )
    assert changed.change_plan(Plan.CLINIC, usage=Usage(0, 0), by=by, now=NOW) is changed


@pytest.mark.parametrize(
    ("solo", "doctors", "plan"),
    [(True, 1, Plan.SOLO), (False, 1, Plan.CLINIC), (False, 3, Plan.CLINIC), (False, 4, Plan.PLUS)],
)
def test_r1_an_approved_applications_plan(solo: bool, doctors: int, plan: Plan) -> None:
    assert plan_for_application(solo=solo, doctors=doctors) is plan
