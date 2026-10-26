"""Suspending and reactivating a clinic (M6c-P4; FR-ONB-05; spec R56-R58).

| Endpoint | Access |
|---|---|
| ``POST /api/v1/ops/clinics/{clinic_id}/suspend`` | ``@ops`` (``OPS_ADMIN``) |
| ``POST /api/v1/ops/clinics/{clinic_id}/reactivate`` | ``@ops`` (``OPS_ADMIN``) |
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.context import Actor
from mediease_api.application.ops.suspension import NOTE_MAX, ReactivateClinic, SuspendClinic
from mediease_api.delivery.http.access import current_principal, ops
from mediease_api.delivery.http.bodies import clinic_body
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.clinics.clinic import SuspendReason


class SuspendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: SuspendReason
    note: str | None = Field(default=None, max_length=NOTE_MAX)


class SuspensionUseCases(Protocol):
    def suspend_clinic(self) -> SuspendClinic: ...
    def reactivate_clinic(self) -> ReactivateClinic: ...


def _actor() -> Actor:
    return Actor.for_user(current_principal().user, request_info())


def create_ops_suspension_blueprint(use_cases: SuspensionUseCases) -> Blueprint:
    bp = Blueprint("ops_suspension", __name__, url_prefix="/api/v1/ops/clinics")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.post("/<uuid:clinic_id>/suspend")
    @ops
    def suspend(clinic_id: UUID) -> Response:
        body = parse_json(SuspendIn)
        result = use_cases.suspend_clinic().execute(_actor(), clinic_id, body.reason, body.note)
        return jsonify(
            {"clinic": clinic_body(result.clinic), "requests_withdrawn": result.withdrawn}
        )

    @bp.post("/<uuid:clinic_id>/reactivate")
    @ops
    def reactivate(clinic_id: UUID) -> Response:
        return jsonify(clinic_body(use_cases.reactivate_clinic().execute(_actor(), clinic_id)))

    return bp
