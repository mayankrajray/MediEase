"""The clinic's fee schedule (M6d-P1; FR-BIL-01; spec billing R1-R12).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/clinic/fees`` | ``BILLING_MANAGE`` |
| ``POST /api/v1/clinic/fees/services`` | ``FEES_MANAGE`` |
| ``PATCH /api/v1/clinic/fees/services/{service_id}`` | ``FEES_MANAGE`` |
| ``PUT /api/v1/clinic/fees/services/{service_id}/doctors/{doctor_id}`` | ``FEES_MANAGE`` |

Each answers the whole schedule, so the screen never computes a price. Amounts are paise.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mediease_api.application.billing.fees import (
    AddService,
    ChangeService,
    FeeSchedule,
    GetFees,
    ServiceCommand,
    SetDoctorPrice,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.billing.fees import MAX_SERVICES, NAME_MAX, ServiceKind
from mediease_api.domain.billing.money import MAX_LINE_PAISE
from mediease_api.domain.identity.permissions import Permission

Price = Field(default=None, ge=0, le=MAX_LINE_PAISE)


class NewServiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=NAME_MAX)
    kind: ServiceKind
    default_price_paise: int | None = Price
    position: int | None = Field(default=None, ge=1, le=MAX_SERVICES)


class ServiceChangeIn(BaseModel):
    """Only the fields sent change; ``default_price_paise: null`` removes the default price."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    kind: ServiceKind | None = None
    default_price_paise: int | None = Price
    active: bool | None = None
    position: int | None = Field(default=None, ge=1, le=MAX_SERVICES)

    @model_validator(mode="after")
    def _at_least_one(self) -> ServiceChangeIn:
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        return self


class DoctorPriceIn(BaseModel):
    """``price_paise: null`` removes the doctor's own price (the default applies)."""

    model_config = ConfigDict(extra="forbid")

    price_paise: int | None = Price


class FeeUseCases(Protocol):
    def get_fees(self) -> GetFees: ...
    def add_service(self) -> AddService: ...
    def change_service(self) -> ChangeService: ...
    def set_doctor_price(self) -> SetDoctorPrice: ...


def fees_body(schedule: FeeSchedule) -> dict[str, Any]:
    return {
        "services": [
            {
                "id": str(s.id),
                "name": s.name,
                "kind": s.kind.value,
                "default_price_paise": s.default_price_paise,
                "active": s.active,
                "position": s.position,
                "doctor_prices": [
                    {
                        "doctor_id": str(d.id),
                        "own_price_paise": schedule.prices.get((s.id, d.id)),
                        "price_paise": schedule.price(s, d.id),
                    }
                    for d in schedule.doctors
                ],
            }
            for s in schedule.services
        ],
        "doctors": [{"id": str(d.id), "display_name": d.display_name} for d in schedule.doctors],
    }


def create_fees_blueprint(use_cases: FeeUseCases) -> Blueprint:
    bp = Blueprint("fees", __name__, url_prefix="/api/v1/clinic/fees")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.BILLING_MANAGE)
    def get_fees() -> Response:
        return jsonify(fees_body(use_cases.get_fees().execute(current_context())))

    @bp.post("/services")
    @clinic(Permission.FEES_MANAGE)
    def add_service() -> tuple[Response, int]:
        body = parse_json(NewServiceIn)
        schedule = use_cases.add_service().execute(
            current_context(),
            ServiceCommand(
                name=body.name,
                kind=body.kind,
                default_price_paise=body.default_price_paise,
                position=body.position,
            ),
        )
        return jsonify(fees_body(schedule)), 201

    @bp.patch("/services/<uuid:service_id>")
    @clinic(Permission.FEES_MANAGE)
    def change_service(service_id: UUID) -> Response:
        body = parse_json(ServiceChangeIn)
        clear = "default_price_paise" in body.model_fields_set and body.default_price_paise is None
        schedule = use_cases.change_service().execute(
            current_context(),
            service_id,
            ServiceCommand(
                name=body.name,
                kind=body.kind,
                default_price_paise=body.default_price_paise,
                clear_default_price=clear,
                active=body.active,
                position=body.position,
            ),
        )
        return jsonify(fees_body(schedule))

    @bp.put("/services/<uuid:service_id>/doctors/<uuid:doctor_id>")
    @clinic(Permission.FEES_MANAGE)
    def set_doctor_price(service_id: UUID, doctor_id: UUID) -> Response:
        body = parse_json(DoctorPriceIn)
        schedule = use_cases.set_doctor_price().execute(
            current_context(), service_id, doctor_id, body.price_paise
        )
        return jsonify(fees_body(schedule))

    return bp
