"""The assistant over HTTP (M7a-P4, P5; FR-AI-01..04; spec assistant §5; ADR-0024).

| Endpoint | Who | What |
|---|---|---|
| ``POST /api/v1/portal/assistant/turns`` | ``@patient`` | one turn; ``context`` names a |
| | | chosen prescription or a verified upload |
| ``POST /api/v1/portal/assistant/confirm`` | ``@patient`` | run a proposed write once |
| ``POST /api/v1/assistant/turns`` | ``@clinic(APPOINTMENTS_MANAGE)`` | one staff turn |
| ``POST /api/v1/assistant/confirm`` | ``@clinic(APPOINTMENTS_MANAGE)`` | a staff proposal, once |

The browser sends the visible conversation (user and assistant text only). Tool calls and their
results never come from, or go to, the client. Every response is ``Cache-Control: no-store``.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mediease_api.application.assistant.engine import (
    MAX_MESSAGE_CHARS,
    MAX_MESSAGES,
    MessageRole,
    TurnMessage,
    TurnReply,
)
from mediease_api.application.assistant.patient import PatientAssistant, PatientContext
from mediease_api.application.assistant.staff import StaffAssistant
from mediease_api.delivery.http.access import clinic, current_context, current_patient, patient
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.patients.patient import Language


class AssistantUseCases(Protocol):
    def patient_assistant(self) -> PatientAssistant: ...
    def staff_assistant(self) -> StaffAssistant: ...


class MessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ContextBody(BaseModel):
    """R9: one chosen prescription, or one verified upload (M7b)."""

    model_config = ConfigDict(extra="forbid")

    prescription_id: UUID | None = None
    upload_id: UUID | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> ContextBody:
        if (self.prescription_id is None) == (self.upload_id is None):
            raise ValueError("name exactly one of prescription_id and upload_id")
        return self


class StaffTurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[MessageBody] = Field(min_length=1, max_length=MAX_MESSAGES)


class PatientTurnBody(StaffTurnBody):
    language: Language | None = None
    context: ContextBody | None = None


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=16, max_length=4096)
    language: Language | None = None


def _messages(body: StaffTurnBody) -> list[TurnMessage]:
    return [TurnMessage(MessageRole(m.role), m.content) for m in body.messages]


def reply_body(reply: TurnReply) -> dict[str, Any]:
    proposal = reply.proposal
    return {
        "kind": reply.kind.value,
        "reply": reply.reply,
        "proposal": (
            {
                "token": proposal.token,
                "summary": proposal.summary,
                "expires_at": proposal.expires_at.isoformat(),
            }
            if proposal
            else None
        ),
    }


def _no_store(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    return response


def create_assistant_blueprint(use_cases: AssistantUseCases) -> Blueprint:
    bp = Blueprint("assistant", __name__, url_prefix="/api/v1")
    bp.after_request(_no_store)

    @bp.post("/portal/assistant/turns")
    @patient
    def patient_turn() -> Response:
        body = parse_json(PatientTurnBody)
        context = (
            PatientContext(body.context.prescription_id, body.context.upload_id)
            if body.context
            else None
        )
        reply = use_cases.patient_assistant().turn(
            current_patient(),
            _messages(body),
            language=body.language,
            context=context,
            info=request_info(),
        )
        return jsonify(reply_body(reply))

    @bp.post("/portal/assistant/confirm")
    @patient
    def patient_confirm() -> Response:
        body = parse_json(ConfirmBody)
        reply = use_cases.patient_assistant().confirm(
            current_patient(), body.token, language=body.language, info=request_info()
        )
        return jsonify(reply_body(reply))

    @bp.post("/assistant/turns")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def staff_turn() -> Response:
        body = parse_json(StaffTurnBody)
        reply = use_cases.staff_assistant().turn(current_context(), _messages(body))
        return jsonify(reply_body(reply))

    @bp.post("/assistant/confirm")
    @clinic(Permission.APPOINTMENTS_MANAGE)
    def staff_confirm() -> Response:
        body = parse_json(ConfirmBody)
        reply = use_cases.staff_assistant().confirm(current_context(), body.token)
        return jsonify(reply_body(reply))

    return bp
