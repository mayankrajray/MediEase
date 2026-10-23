"""The notification centre and preferences (M6a-P7; FR-NTF-03, FR-NTF-05).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/notifications?limit=`` | ``CLINIC_VIEW`` |
| ``GET /api/v1/notifications/summary`` | ``CLINIC_VIEW`` (ETag, 304) |
| ``POST /api/v1/notifications/{id}/read`` | ``CLINIC_VIEW`` |
| ``POST /api/v1/notifications/read-all`` | ``CLINIC_VIEW`` |
| ``GET/PUT /api/v1/notifications/preferences`` | ``CLINIC_VIEW`` |

Every clinic role holds ``CLINIC_VIEW``; each route acts on the caller's own notifications only,
so another member's or clinic's is 404. Bodies are titles from a non-clinical catalogue, links and
times. Never cached.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.notifications.use_cases import (
    GetNotificationPreferences,
    GetNotificationSummary,
    ListNotifications,
    PreferenceChange,
    PreferenceView,
    ReadAllNotifications,
    ReadNotification,
    SetNotificationPreferences,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.etag import conditional_json
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.notifications.notification import Channel, Notification, NotificationKind
from mediease_api.domain.shared.errors import InvalidValue

LIST_DEFAULT = 30


class NotificationUseCases(Protocol):
    def list_notifications(self) -> ListNotifications: ...
    def notification_summary(self) -> GetNotificationSummary: ...
    def read_notification(self) -> ReadNotification: ...
    def read_all_notifications(self) -> ReadAllNotifications: ...
    def notification_preferences(self) -> GetNotificationPreferences: ...
    def set_notification_preferences(self) -> SetNotificationPreferences: ...


class PreferenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: NotificationKind
    channel: Channel = Channel.IN_APP
    enabled: bool


class PreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PreferenceItem] = Field(min_length=1, max_length=len(NotificationKind) * 4)


def notification_body(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "kind": n.kind.value,
        "title": n.title,
        "link": n.link,
        "entity_type": n.entity_type,
        "entity_id": str(n.entity_id),
        "created_at": n.created_at.isoformat(),
        "read_at": n.read_at.isoformat() if n.read_at else None,
    }


def _preferences_body(views: list[PreferenceView]) -> dict[str, Any]:
    return {
        "items": [
            {
                "kind": v.kind.value,
                "label": v.label,
                "channel": v.channel.value,
                "enabled": v.enabled,
            }
            for v in views
        ]
    }


def create_notifications_blueprint(use_cases: NotificationUseCases) -> Blueprint:
    bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.CLINIC_VIEW)
    def list_notifications() -> Response:
        raw = request.args.get("limit")
        try:
            limit = int(raw) if raw is not None else LIST_DEFAULT
        except ValueError:
            raise InvalidValue("limit", "must be a whole number") from None
        items = use_cases.list_notifications().execute(current_context(), limit=limit)
        return jsonify({"items": [notification_body(n) for n in items]})

    @bp.get("/summary")
    @clinic(Permission.CLINIC_VIEW)
    def notification_summary() -> Response:
        summary = use_cases.notification_summary().execute(current_context())
        return conditional_json(
            {
                "unread": summary.unread,
                "latest_id": str(summary.latest_id) if summary.latest_id else None,
            }
        )

    @bp.post("/<uuid:notification_id>/read")
    @clinic(Permission.CLINIC_VIEW)
    def read_notification(notification_id: UUID) -> Response:
        read = use_cases.read_notification().execute(current_context(), notification_id)
        return jsonify(notification_body(read))

    @bp.post("/read-all")
    @clinic(Permission.CLINIC_VIEW)
    def read_all_notifications() -> Response:
        updated = use_cases.read_all_notifications().execute(current_context())
        return jsonify({"updated": updated})

    @bp.get("/preferences")
    @clinic(Permission.CLINIC_VIEW)
    def notification_preferences() -> Response:
        return jsonify(
            _preferences_body(use_cases.notification_preferences().execute(current_context()))
        )

    @bp.put("/preferences")
    @clinic(Permission.CLINIC_VIEW)
    def set_notification_preferences() -> Response:
        body = parse_json(PreferencesRequest)
        views = use_cases.set_notification_preferences().execute(
            current_context(),
            [
                PreferenceChange(kind=i.kind, channel=i.channel, enabled=i.enabled)
                for i in body.items
            ],
        )
        return jsonify(_preferences_body(views))

    return bp
