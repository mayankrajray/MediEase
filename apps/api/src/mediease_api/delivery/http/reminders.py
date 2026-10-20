"""Reminders and pending follow-ups (M5-P4; FR-REM-02, 05, 07; spec R3, R17).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/patients/{patient_id}/reminders`` | ``REMINDERS_SCHEDULE`` |
| ``POST /api/v1/patients/{patient_id}/reminders`` | ``REMINDERS_SCHEDULE`` |
| ``PATCH /api/v1/reminders/{reminder_id}`` | ``REMINDERS_SCHEDULE`` |
| ``GET /api/v1/follow-ups/pending`` | ``REMINDERS_SCHEDULE`` |
| ``GET /api/v1/patients/{patient_id}/messages`` | ``REMINDERS_SCHEDULE`` (M5-P6) |

Every role holds ``REMINDERS_SCHEDULE``. Another clinic's patient or reminder is a 404 (NFR-08).
The bodies carry dates, IDs and statuses only: nothing clinical, and a message's variables and
number never appear.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict

from mediease_api.application.reminders.use_cases import (
    ChangeCommand,
    ChangeReminder,
    ListPatientMessages,
    ListPatientReminders,
    ListPendingFollowUps,
    ScheduleCommand,
    ScheduleReminder,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.messaging.message import Message
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.ports.reminders import PendingFollowUp, ReminderRead

PENDING_DEFAULT_LIMIT = 50


class ReminderUseCases(Protocol):
    def schedule_reminder(self) -> ScheduleReminder: ...
    def change_reminder(self) -> ChangeReminder: ...
    def list_patient_reminders(self) -> ListPatientReminders: ...
    def list_pending_follow_ups(self) -> ListPendingFollowUps: ...
    def list_patient_messages(self) -> ListPatientMessages: ...


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: UUID
    follow_up_date: date


class ChangeRequest(BaseModel):
    """Exactly one of the two (checked by the use case)."""

    model_config = ConfigDict(extra="forbid")

    follow_up_date: date | None = None
    cancel: bool = False


def reminder_body(read: ReminderRead) -> dict[str, Any]:
    r = read.reminder
    return {
        "id": str(r.id),
        "patient_id": str(r.patient_id),
        "doctor_id": str(r.doctor_id),
        "kind": r.kind.value,
        "source": r.source.value,
        "prescription_id": str(r.source_id) if r.source_id else None,
        "follow_up_date": r.follow_up_date.isoformat(),
        "due_at": r.due_at.isoformat(),
        # FR-REM-05: the message's status once sent (decision 3A), else the reminder's own.
        "status": read.visible_status,
        "error_code": read.message_error or r.error_code,
        "revision": r.revision,
        "created_at": r.created_at.isoformat(),
        "cancelled_at": r.cancelled_at.isoformat() if r.cancelled_at else None,
    }


def pending_body(item: PendingFollowUp) -> dict[str, Any]:
    return {
        "patient_id": str(item.patient_id),
        "patient_code": item.patient_code,
        "patient_name": item.patient_name,
        "doctor_id": str(item.doctor_id),
        "prescription_id": str(item.prescription_id),
        "visit_id": str(item.visit_id),
        "follow_up_date": item.follow_up_date.isoformat(),
        "reminder_status": item.reminder_status,
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def message_body(m: Message) -> dict[str, Any]:
    """Status only (decision 1A): never the variables or the number."""
    return {
        "id": str(m.id),
        "template_key": m.template_key,
        "source_type": m.source_type.value,
        "source_id": str(m.source_id),
        "channel": m.channel.value,
        "status": m.status.value,
        "error_code": m.error_code,
        "created_at": m.created_at.isoformat(),
        "sent_at": _iso(m.sent_at),
        "delivered_at": _iso(m.delivered_at),
        "read_at": _iso(m.read_at),
        "failed_at": _iso(m.failed_at),
    }


def _int_arg(name: str, default: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise InvalidValue(name, "must be a whole number") from None


def create_reminders_blueprint(use_cases: ReminderUseCases) -> Blueprint:
    bp = Blueprint("reminders", __name__, url_prefix="/api/v1")
    patient = "/patients/<uuid:patient_id>/reminders"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get(patient)
    @clinic(Permission.REMINDERS_SCHEDULE)
    def list_patient_reminders(patient_id: UUID) -> Response:
        reads = use_cases.list_patient_reminders().execute(current_context(), patient_id=patient_id)
        return jsonify({"items": [reminder_body(r) for r in reads]})

    @bp.post(patient)
    @clinic(Permission.REMINDERS_SCHEDULE)
    def schedule_reminder(patient_id: UUID) -> tuple[Response, int]:
        body = parse_json(ScheduleRequest)
        read = use_cases.schedule_reminder().execute(
            current_context(),
            patient_id=patient_id,
            cmd=ScheduleCommand(doctor_id=body.doctor_id, follow_up_date=body.follow_up_date),
        )
        return jsonify(reminder_body(read)), 201

    @bp.patch("/reminders/<uuid:reminder_id>")
    @clinic(Permission.REMINDERS_SCHEDULE)
    def change_reminder(reminder_id: UUID) -> Response:
        body = parse_json(ChangeRequest)
        read = use_cases.change_reminder().execute(
            current_context(),
            reminder_id=reminder_id,
            cmd=ChangeCommand(follow_up_date=body.follow_up_date, cancel=body.cancel),
        )
        return jsonify(reminder_body(read))

    @bp.get("/follow-ups/pending")
    @clinic(Permission.REMINDERS_SCHEDULE)
    def list_pending_follow_ups() -> Response:
        limit = _int_arg("limit", PENDING_DEFAULT_LIMIT)
        offset = _int_arg("offset", 0)
        items = use_cases.list_pending_follow_ups().execute(
            current_context(), limit=limit, offset=offset
        )
        return jsonify(
            {"items": [pending_body(i) for i in items], "limit": limit, "offset": offset}
        )

    @bp.get("/patients/<uuid:patient_id>/messages")
    @clinic(Permission.REMINDERS_SCHEDULE)
    def list_patient_messages(patient_id: UUID) -> Response:
        messages = use_cases.list_patient_messages().execute(
            current_context(), patient_id=patient_id
        )
        return jsonify({"items": [message_body(m) for m in messages]})

    return bp
