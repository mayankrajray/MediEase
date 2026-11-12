"""Web push devices over HTTP (M7e-E2, ADR-0025; spec web-push R10-R19).

- ``GET /api/v1/push/config`` (public): whether push is offered, and the VAPID public key.
- ``/api/v1/portal/push-subscriptions`` (``@patient``) and ``/api/v1/me/push-subscriptions``
  (``@authenticated``, staff, any clinic): add or refresh this browser (``POST``), list the
  caller's devices (``GET``), turn one off (``DELETE /{id}``). The owner is the session's account
  or user. Unsafe methods need the CSRF token (``csrf.py``); answers are never cached.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.push.subscriptions import (
    DeviceView,
    GetPushConfig,
    ListDevices,
    RemoveDevice,
    SubscribeDevice,
)
from mediease_api.delivery.http.access import (
    authenticated,
    current_patient,
    current_principal,
    patient,
    public,
)
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.push.subscription import ENDPOINT_MAX, PushOwner


class PushUseCases(Protocol):
    def push_config(self) -> GetPushConfig: ...
    def subscribe_device(self) -> SubscribeDevice: ...
    def list_devices(self) -> ListDevices: ...
    def remove_device(self) -> RemoveDevice: ...


class KeysIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str = Field(min_length=1, max_length=128)
    auth: str = Field(min_length=1, max_length=64)


class SubscriptionIn(BaseModel):
    """What ``PushSubscription.toJSON()`` gives in the browser; ``expirationTime`` is ignored."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    endpoint: str = Field(min_length=1, max_length=ENDPOINT_MAX)
    expiration_time: int | None = Field(default=None, alias="expirationTime")
    keys: KeysIn


def device_body(d: DeviceView) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "label": d.label,
        "created_at": d.created_at.isoformat(),
        "last_success_at": d.last_success_at.isoformat() if d.last_success_at else None,
        "active": d.active,
    }


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


def _devices_blueprint(
    name: str, prefix: str, use_cases: PushUseCases, *, for_patient: bool
) -> Blueprint:
    bp = Blueprint(name, __name__, url_prefix=prefix)
    bp.after_request(_no_store)
    guard = patient if for_patient else authenticated

    def owner() -> PushOwner:
        if for_patient:
            return PushOwner.patient(current_patient().account_id)
        return PushOwner.staff(current_principal().user_id)

    @bp.post("")
    @guard
    def subscribe() -> tuple[Response, int]:
        body = parse_json(SubscriptionIn)
        result = use_cases.subscribe_device().execute(
            owner(),
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            user_agent=request.headers.get("User-Agent"),
            info=request_info(),
        )
        return jsonify(device_body(result.device)), 201 if result.created else 200

    @bp.get("")
    @guard
    def list_devices() -> Response:
        return jsonify(
            {"items": [device_body(d) for d in use_cases.list_devices().execute(owner())]}
        )

    @bp.delete("/<uuid:device_id>")
    @guard
    def remove(device_id: UUID) -> tuple[str, int]:
        use_cases.remove_device().execute(owner(), device_id, request_info())
        return "", 204

    return bp


def create_push_blueprints(use_cases: PushUseCases) -> list[Blueprint]:
    config = Blueprint("push_config", __name__, url_prefix="/api/v1/push")
    config.after_request(_no_store)

    @config.get("/config")
    @public
    def push_config() -> Response:
        c = use_cases.push_config().execute()
        return jsonify({"enabled": c.enabled, "public_key": c.public_key})

    return [
        config,
        _devices_blueprint(
            "portal_push", "/api/v1/portal/push-subscriptions", use_cases, for_patient=True
        ),
        _devices_blueprint(
            "staff_push", "/api/v1/me/push-subscriptions", use_cases, for_patient=False
        ),
    ]
