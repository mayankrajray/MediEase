"""A doctor's favourites, templates and medicine suggestions (M4-P3; FR-RX-05, FR-RX-10).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/rx-favourites`` · ``POST`` | ``CLINICAL_WRITE`` |
| ``PUT /api/v1/rx-favourites/{id}`` · ``DELETE`` | ``CLINICAL_WRITE`` (its doctor) |
| ``GET /api/v1/rx-templates`` · ``POST`` | ``CLINICAL_WRITE`` |
| ``GET /api/v1/rx-templates/{id}`` · ``PUT`` · ``DELETE`` | ``CLINICAL_WRITE`` (its doctor) |
| ``GET /api/v1/medicine-suggestions?q=`` | ``CLINICAL_WRITE`` |

Only prescribing doctors need these, so front desk and owners who are not doctors get 403;
another doctor's favourite or template is a 404. Suggestions come from this clinic's issued
prescriptions and the caller's favourites only (FR-RX-10, AC5). Never cached.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.prescriptions.library import (
    DeleteFavourite,
    DeleteTemplate,
    FavouriteInput,
    GetTemplate,
    ListFavourites,
    ListTemplates,
    SaveFavourite,
    SaveTemplate,
    SuggestMedicines,
    TemplateInput,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import item_body
from mediease_api.delivery.http.prescriptions import AdviceRequest, ItemRequest, item_input
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.prescriptions import prescription as limits
from mediease_api.domain.prescriptions.library import NAME_MAX, Favourite, Template
from mediease_api.domain.prescriptions.prescription import Advice


class LibraryUseCases(Protocol):
    def list_favourites(self) -> ListFavourites: ...
    def save_favourite(self) -> SaveFavourite: ...
    def delete_favourite(self) -> DeleteFavourite: ...
    def list_templates(self) -> ListTemplates: ...
    def get_template(self) -> GetTemplate: ...
    def save_template(self) -> SaveTemplate: ...
    def delete_template(self) -> DeleteTemplate: ...
    def suggest_medicines(self) -> SuggestMedicines: ...


class FavouriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=NAME_MAX)
    item: ItemRequest
    revision: int | None = Field(default=None, ge=1)


class TemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=NAME_MAX)
    items: list[ItemRequest] = Field(default_factory=list, max_length=limits.MAX_ITEMS)
    advice: AdviceRequest = Field(default_factory=AdviceRequest)
    follow_up_days: int | None = None
    revision: int | None = Field(default=None, ge=1)


def _favourite_input(body: FavouriteRequest) -> FavouriteInput:
    return FavouriteInput(
        name=body.name, item=item_input(0, body.item, at="item"), seen_revision=body.revision
    )


def _template_input(body: TemplateRequest) -> TemplateInput:
    return TemplateInput(
        name=body.name,
        items=[item_input(i, item) for i, item in enumerate(body.items)],
        advice=Advice.create(
            diet=body.advice.diet,
            activity=body.advice.activity,
            return_if=body.advice.return_if,
            notes=body.advice.notes,
        ),
        follow_up_days=body.follow_up_days,
        seen_revision=body.revision,
    )


def favourite_body(fav: Favourite) -> dict[str, Any]:
    item = item_body(fav.item)
    for identity in ("id", "position", "favourite_id"):
        item.pop(identity)
    return {
        "id": str(fav.id),
        "name": fav.name,
        "item": item,
        "revision": fav.revision,
        "use_count": fav.use_count,
        "last_used_at": fav.last_used_at.isoformat() if fav.last_used_at else None,
        "updated_at": fav.updated_at.isoformat(),
    }


def template_body(template: Template) -> dict[str, Any]:
    items = []
    for line in template.items:
        item = item_body(line)
        for identity in ("id", "position", "favourite_id"):
            item.pop(identity)
        items.append(item)
    return {
        "id": str(template.id),
        "name": template.name,
        "items": items,
        "advice": template.advice.as_json(),
        "follow_up_days": template.follow_up_days,
        "revision": template.revision,
        "use_count": template.use_count,
        "last_used_at": template.last_used_at.isoformat() if template.last_used_at else None,
        "updated_at": template.updated_at.isoformat(),
    }


def create_rx_library_blueprint(use_cases: LibraryUseCases) -> Blueprint:
    bp = Blueprint("rx_library", __name__, url_prefix="/api/v1")
    fav_one = "/rx-favourites/<uuid:favourite_id>"
    tpl_one = "/rx-templates/<uuid:template_id>"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("/rx-favourites")
    @clinic(Permission.CLINICAL_WRITE)
    def list_favourites() -> Response:
        favs = use_cases.list_favourites().execute(current_context())
        return jsonify({"items": [favourite_body(f) for f in favs]})

    @bp.post("/rx-favourites")
    @clinic(Permission.CLINICAL_WRITE)
    def create_favourite() -> tuple[Response, int]:
        body = parse_json(FavouriteRequest)
        fav = use_cases.save_favourite().execute(current_context(), _favourite_input(body))
        return jsonify(favourite_body(fav)), 201

    @bp.put(fav_one)
    @clinic(Permission.CLINICAL_WRITE)
    def replace_favourite(favourite_id: UUID) -> Response:
        body = parse_json(FavouriteRequest)
        fav = use_cases.save_favourite().execute(
            current_context(), _favourite_input(body), favourite_id=favourite_id
        )
        return jsonify(favourite_body(fav))

    @bp.delete(fav_one)
    @clinic(Permission.CLINICAL_WRITE)
    def delete_favourite(favourite_id: UUID) -> tuple[str, int]:
        use_cases.delete_favourite().execute(current_context(), favourite_id=favourite_id)
        return "", 204

    @bp.get("/rx-templates")
    @clinic(Permission.CLINICAL_WRITE)
    def list_templates() -> Response:
        templates = use_cases.list_templates().execute(current_context())
        return jsonify({"items": [template_body(t) for t in templates]})

    @bp.post("/rx-templates")
    @clinic(Permission.CLINICAL_WRITE)
    def create_template() -> tuple[Response, int]:
        body = parse_json(TemplateRequest)
        template = use_cases.save_template().execute(current_context(), _template_input(body))
        return jsonify(template_body(template)), 201

    @bp.get(tpl_one)
    @clinic(Permission.CLINICAL_WRITE)
    def get_template(template_id: UUID) -> Response:
        template = use_cases.get_template().execute(current_context(), template_id=template_id)
        return jsonify(template_body(template))

    @bp.put(tpl_one)
    @clinic(Permission.CLINICAL_WRITE)
    def replace_template(template_id: UUID) -> Response:
        body = parse_json(TemplateRequest)
        template = use_cases.save_template().execute(
            current_context(), _template_input(body), template_id=template_id
        )
        return jsonify(template_body(template))

    @bp.delete(tpl_one)
    @clinic(Permission.CLINICAL_WRITE)
    def delete_template(template_id: UUID) -> tuple[str, int]:
        use_cases.delete_template().execute(current_context(), template_id=template_id)
        return "", 204

    @bp.get("/medicine-suggestions")
    @clinic(Permission.CLINICAL_WRITE)
    def suggest_medicines() -> Response:
        found = use_cases.suggest_medicines().execute(
            current_context(), query=request.args.get("q", "")
        )
        return jsonify(
            {
                "items": [
                    {
                        "name": s.name,
                        "source": s.source.value,
                        "uses": s.uses,
                        "favourite_id": str(s.favourite_id) if s.favourite_id else None,
                    }
                    for s in found
                ]
            }
        )

    return bp
