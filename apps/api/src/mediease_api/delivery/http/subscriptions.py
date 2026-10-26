"""Plans and the trial (M6d-P7; FR-SUB-01; spec plans-and-trial R6-R8).

| Endpoint | Access |
|---|---|
| ``GET /api/v1/clinic/subscription`` | ``CLINIC_MANAGE`` (owners): plan, limits, usage, trial |
| ``PUT /api/v1/ops/clinics/{clinic_id}/plan`` | ``@ops`` (``OPS_ADMIN``): set the plan, audited |

The ops clinic list carries each clinic's plan and trial (``plan_summary_body``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict

from mediease_api.application.context import Actor
from mediease_api.application.subscriptions.plans import GetSubscription, SetPlan, SubscriptionView
from mediease_api.delivery.http.access import clinic, current_context, current_principal, ops
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.subscriptions.subscription import PLAN_NAMES, Plan, Subscription


class SubscriptionUseCases(Protocol):
    def get_subscription(self) -> GetSubscription: ...
    def set_plan(self) -> SetPlan: ...


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: Plan


def plan_summary_body(subscription: Subscription, now: datetime) -> dict[str, Any]:
    """The plan and the trial: what ops see per clinic, and the head of the owner's view."""
    return {
        "plan": subscription.plan.value,
        "plan_name": PLAN_NAMES[subscription.plan],
        "trial_state": subscription.trial_state(now).value,
        "trial_ends_at": subscription.trial_ends_at.isoformat()
        if subscription.trial_ends_at
        else None,
        "trial_days_left": subscription.days_left(now),
    }


def subscription_body(view: SubscriptionView) -> dict[str, Any]:
    limits = view.subscription.limits
    return {
        **plan_summary_body(view.subscription, view.now),
        "trial_started_at": view.subscription.trial_started_at.isoformat()
        if view.subscription.trial_started_at
        else None,
        "limits": {"doctors": limits.doctors, "users": limits.users},
        "usage": {"doctors": view.usage.doctors, "users": view.usage.users},
    }


def create_subscriptions_blueprint(use_cases: SubscriptionUseCases) -> Blueprint:
    bp = Blueprint("subscriptions", __name__, url_prefix="/api/v1")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("/clinic/subscription")
    @clinic(Permission.CLINIC_MANAGE)
    def get_subscription() -> Response:
        return jsonify(subscription_body(use_cases.get_subscription().execute(current_context())))

    @bp.put("/ops/clinics/<uuid:clinic_id>/plan")
    @ops
    def set_plan(clinic_id: UUID) -> Response:
        body = parse_json(PlanIn)
        actor = Actor.for_user(current_principal().user, request_info())
        return jsonify(subscription_body(use_cases.set_plan().execute(actor, clinic_id, body.plan)))

    return bp
