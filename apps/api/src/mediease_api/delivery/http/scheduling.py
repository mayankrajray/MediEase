"""Schedules, exceptions and sessions (M3-P1; FR-APT-01, FR-APT-02, spec R1-R4, R14-R20).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/clinic/doctors/{doctor_id}/schedule`` | ``DOCTORS_VIEW`` |
| ``PUT /api/v1/clinic/doctors/{doctor_id}/schedule`` | ``SCHEDULES_MANAGE`` |
| ``POST /api/v1/clinic/doctors/{doctor_id}/schedule-exceptions`` | ``SCHEDULES_MANAGE`` |
| ``DELETE .../schedule-exceptions/{exception_id}`` | ``SCHEDULES_MANAGE`` |
| ``GET /api/v1/sessions?date=&doctor_id=`` | ``APPOINTMENTS_MANAGE`` |

The clinic comes from the request context, so another clinic's doctor or exception is a 404
(NFR-08). Times in bodies are the clinic's wall-clock ``HH:MM``; session instants are UTC with an
offset, which the web app shows in the clinic's zone.
"""

from __future__ import annotations

from datetime import date, time
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.context import Actor
from mediease_api.application.scheduling.exceptions import (
    AddException,
    ExceptionCommand,
    RemoveException,
)
from mediease_api.application.scheduling.schedules import (
    MAX_BLOCKS,
    BlockCommand,
    GetSchedule,
    ReplaceSchedule,
)
from mediease_api.application.scheduling.sessions import ListSessions
from mediease_api.application.scheduling.views import ExceptionChange, ScheduleChange
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import (
    exception_body,
    items_body,
    schedule_body,
    session_body,
)
from mediease_api.delivery.http.validation import RequestValidationFailed, parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.scheduling.exceptions import ExceptionKind


class SchedulingUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def get_schedule(self) -> GetSchedule: ...
    def replace_schedule(self) -> ReplaceSchedule: ...
    def add_schedule_exception(self) -> AddException: ...
    def remove_schedule_exception(self) -> RemoveException: ...
    def list_sessions(self) -> ListSessions: ...


class BlockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: int = Field(ge=0, le=6)
    start_time: time
    # At or before start_time: the block ends the next day (decision D2), at most 12 hours.
    end_time: time
    slot_minutes: int | None = Field(default=None, ge=5, le=120)
    capacity: int | None = Field(default=None, ge=1, le=500)

    def command(self) -> BlockCommand:
        return BlockCommand(
            weekday=self.weekday,
            start_time=self.start_time,
            end_time=self.end_time,
            slot_minutes=self.slot_minutes,
            capacity=self.capacity,
        )


class ScheduleRequest(BaseModel):
    """The whole weekly schedule: it replaces the current one (R16). An empty list clears it."""

    model_config = ConfigDict(extra="forbid")

    blocks: list[BlockRequest] = Field(max_length=MAX_BLOCKS)


class ExceptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ExceptionKind
    on_date: date
    # EXTRA only; refused for LEAVE, which covers the whole day (D8).
    start_time: time | None = None
    end_time: time | None = None
    slot_minutes: int | None = Field(default=None, ge=5, le=120)
    capacity: int | None = Field(default=None, ge=1, le=500)
    note: str | None = Field(default=None, max_length=200)

    def command(self) -> ExceptionCommand:
        if self.kind is ExceptionKind.LEAVE and any(
            v is not None
            for v in (self.start_time, self.end_time, self.slot_minutes, self.capacity)
        ):
            raise RequestValidationFailed(
                [{"field": "kind", "reason": "leave covers the whole day: send no times"}]
            )
        return ExceptionCommand(
            kind=self.kind,
            on_date=self.on_date,
            start_time=self.start_time,
            end_time=self.end_time,
            slot_minutes=self.slot_minutes,
            capacity=self.capacity,
            note=self.note,
        )


def schedule_change_body(change: ScheduleChange) -> dict[str, Any]:
    return {
        **schedule_body(change.schedule),
        "kept_sessions": [session_body(s) for s in change.kept_sessions],
    }


def exception_change_body(change: ExceptionChange) -> dict[str, Any]:
    return {
        "exception": exception_body(change.exception),
        "kept_sessions": [session_body(s) for s in change.kept_sessions],
    }


def create_scheduling_blueprint(use_cases: SchedulingUseCases) -> Blueprint:
    bp = Blueprint("scheduling", __name__, url_prefix="/api/v1")
    doctor_path = "/clinic/doctors/<uuid:doctor_id>"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        # Per-tenant data that changes as staff book: never cached.
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get(f"{doctor_path}/schedule")
    @clinic(Permission.DOCTORS_VIEW)
    def get_schedule(doctor_id: UUID) -> Response:
        return jsonify(
            schedule_body(use_cases.get_schedule().execute(current_context(), doctor_id))
        )

    @bp.put(f"{doctor_path}/schedule")
    @clinic(Permission.SCHEDULES_MANAGE)
    def replace_schedule(doctor_id: UUID) -> Response:
        body = parse_json(ScheduleRequest)
        ctx = current_context()
        change = use_cases.replace_schedule().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            doctor_id=doctor_id,
            blocks=[b.command() for b in body.blocks],
        )
        return jsonify(schedule_change_body(change))

    @bp.post(f"{doctor_path}/schedule-exceptions")
    @clinic(Permission.SCHEDULES_MANAGE)
    def add_exception(doctor_id: UUID) -> tuple[Response, int]:
        body = parse_json(ExceptionRequest)
        ctx = current_context()
        change = use_cases.add_schedule_exception().execute(
            clinic_id=ctx.clinic_id, actor=Actor.staff(ctx), doctor_id=doctor_id, cmd=body.command()
        )
        return jsonify(exception_change_body(change)), 201

    @bp.delete(f"{doctor_path}/schedule-exceptions/<uuid:exception_id>")
    @clinic(Permission.SCHEDULES_MANAGE)
    def remove_exception(doctor_id: UUID, exception_id: UUID) -> Response:
        ctx = current_context()
        change = use_cases.remove_schedule_exception().execute(
            clinic_id=ctx.clinic_id,
            actor=Actor.staff(ctx),
            doctor_id=doctor_id,
            exception_id=exception_id,
        )
        return jsonify(exception_change_body(change))

    @bp.get("/sessions")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def list_sessions() -> Response:
        on_date = _date_arg("date")
        doctor_id = _uuid_arg("doctor_id")
        sessions = use_cases.list_sessions().execute(
            current_context(), on_date, doctor_id=doctor_id
        )
        return jsonify(items_body(session_body(s) for s in sessions))

    return bp


def _date_arg(name: str) -> date:
    raw = request.args.get(name)
    if raw is None:
        raise RequestValidationFailed([{"field": name, "reason": "is required"}])
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise RequestValidationFailed(
            [{"field": name, "reason": "must be a date like 2026-10-20"}]
        ) from None


def _uuid_arg(name: str) -> UUID | None:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    try:
        return UUID(raw)
    except ValueError:
        raise RequestValidationFailed([{"field": name, "reason": "must be an ID"}]) from None
