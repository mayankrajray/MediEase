"""Prescriptions: draft, read, replace, discard, issue, revise (M4-P2; FR-RX-01..03, 06, 09).

| Endpoint | Permission |
|---|---|
| ``POST /api/v1/visits/{visit_id}/prescriptions`` | ``CLINICAL_WRITE`` (and the visit's doctor) |
| ``GET /api/v1/prescriptions/{rx_id}`` | ``CLINICAL_VIEW`` |
| ``PUT /api/v1/prescriptions/{rx_id}`` | ``CLINICAL_WRITE`` (and the visit's doctor) |
| ``DELETE /api/v1/prescriptions/{rx_id}`` | ``CLINICAL_WRITE`` (and the visit's doctor) |
| ``POST /api/v1/prescriptions/{rx_id}/issue`` | ``CLINICAL_WRITE`` (and the visit's doctor) |
| ``POST /api/v1/prescriptions/{rx_id}/revise`` | ``CLINICAL_WRITE`` (and the visit's doctor) |
| ``GET /api/v1/prescriptions/{rx_id}/pdf`` | ``RX_PRINT`` (superseded: + ``CLINICAL_VIEW``) |
| ``GET /api/v1/patients/{patient_id}/prescriptions`` | ``RX_PRINT`` (M4-P4; no content) |

Front desk holds neither clinical permission (spec §2); it may print (``RX_PRINT``, spec D6).
Clinical content: never logged or cached, and validation errors name the field and the rule,
never the value (R17).
"""

from __future__ import annotations

from datetime import date
from typing import Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.prescriptions.pdf import (
    PDF_CONTENT_TYPE,
    DownloadPrescriptionPdf,
    ListPrintable,
)
from mediease_api.application.prescriptions.use_cases import (
    CreateDraft,
    DiscardDraft,
    DraftBody,
    GetPrescription,
    IssuePrescription,
    ItemInput,
    ReplaceDraft,
    RevisePrescription,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.bodies import items_body, prescription_body, printable_body
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.prescriptions import prescription as limits
from mediease_api.domain.prescriptions.prescription import Advice
from mediease_api.domain.prescriptions.vocabulary import (
    PHRASE_TEXT_MAX,
    Frequency,
    Preparation,
    PreparationCode,
    Storage,
    StorageCode,
    Timing,
)


class PrescriptionUseCases(Protocol):
    """Fresh use cases for one request, supplied by bootstrap.py."""

    def create_prescription(self) -> CreateDraft: ...
    def get_prescription(self) -> GetPrescription: ...
    def replace_prescription(self) -> ReplaceDraft: ...
    def discard_prescription(self) -> DiscardDraft: ...
    def issue_prescription(self) -> IssuePrescription: ...
    def revise_prescription(self) -> RevisePrescription: ...
    def download_prescription_pdf(self) -> DownloadPrescriptionPdf: ...
    def list_printable(self) -> ListPrintable: ...


class PreparationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: PreparationCode
    text: str | None = Field(default=None, max_length=PHRASE_TEXT_MAX)


class StorageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: StorageCode
    days: int | None = None


class ItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    medicine_name: str = Field(max_length=limits.NAME_MAX)
    form: str | None = Field(default=None, max_length=limits.SHORT_MAX)
    strength: str | None = Field(default=None, max_length=limits.SHORT_MAX)
    dose: str | None = Field(default=None, max_length=limits.SHORT_MAX)
    frequency: Frequency | None = None
    frequency_text: str | None = Field(default=None, max_length=limits.SHORT_MAX)
    timing: Timing | None = None
    duration_days: int | None = None
    quantity: str | None = Field(default=None, max_length=limits.SHORT_MAX)
    preparation: list[PreparationRequest] = Field(
        default_factory=list, max_length=limits.MAX_PREPARATIONS
    )
    storage: list[StorageRequest] = Field(default_factory=list, max_length=limits.MAX_STORAGE)
    warnings: str | None = Field(default=None, max_length=limits.WARNINGS_MAX)
    notes: str | None = Field(default=None, max_length=limits.ITEM_NOTES_MAX)
    # M4-P3: the favourite this line came from (counted at issue).
    favourite_id: UUID | None = None


class AdviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diet: list[str] = Field(default_factory=list, max_length=limits.MAX_ADVICE_ENTRIES)
    activity: list[str] = Field(default_factory=list, max_length=limits.MAX_ADVICE_ENTRIES)
    return_if: list[str] = Field(default_factory=list, max_length=limits.MAX_ADVICE_ENTRIES)
    notes: str | None = Field(default=None, max_length=limits.ADVICE_NOTES_MAX)


class DraftRequest(BaseModel):
    """The whole draft (decision 3A); ``revision`` is the one the screen has."""

    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    items: list[ItemRequest] = Field(default_factory=list, max_length=limits.MAX_ITEMS)
    advice: AdviceRequest = Field(default_factory=AdviceRequest)
    follow_up_date: date | None = None
    # M4-P3: the template the body came from (counted at issue).
    template_id: UUID | None = None


class IssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)


def item_input(i: int, item: ItemRequest, at: str | None = None) -> ItemInput:
    at = at or f"items.{i}"
    return ItemInput(
        medicine_name=item.medicine_name,
        form=item.form,
        strength=item.strength,
        dose=item.dose,
        frequency=item.frequency,
        frequency_text=item.frequency_text,
        timing=item.timing,
        duration_days=item.duration_days,
        quantity=item.quantity,
        preparation=tuple(
            Preparation.of(p.code, p.text, f"{at}.preparation.{j}")
            for j, p in enumerate(item.preparation)
        ),
        storage=tuple(
            Storage.of(s.code, s.days, f"{at}.storage.{j}") for j, s in enumerate(item.storage)
        ),
        warnings=item.warnings,
        notes=item.notes,
        favourite_id=item.favourite_id,
    )


def create_prescriptions_blueprint(use_cases: PrescriptionUseCases) -> Blueprint:
    bp = Blueprint("prescriptions", __name__, url_prefix="/api/v1")
    one = "/prescriptions/<uuid:rx_id>"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @bp.post("/visits/<uuid:visit_id>/prescriptions")
    @clinic(Permission.CLINICAL_WRITE)
    def create_prescription(visit_id: UUID) -> tuple[Response, int]:
        view = use_cases.create_prescription().execute(current_context(), visit_id=visit_id)
        return jsonify(prescription_body(view)), 201

    @bp.get(one)
    @clinic(Permission.CLINICAL_VIEW)
    def get_prescription(rx_id: UUID) -> Response:
        view = use_cases.get_prescription().execute(current_context(), rx_id=rx_id)
        return jsonify(prescription_body(view))

    @bp.put(one)
    @clinic(Permission.CLINICAL_WRITE)
    def replace_prescription(rx_id: UUID) -> Response:
        body = parse_json(DraftRequest)
        draft = DraftBody(
            seen_revision=body.revision,
            items=[item_input(i, item) for i, item in enumerate(body.items)],
            advice=Advice.create(
                diet=body.advice.diet,
                activity=body.advice.activity,
                return_if=body.advice.return_if,
                notes=body.advice.notes,
            ),
            follow_up_date=body.follow_up_date,
            template_id=body.template_id,
        )
        view = use_cases.replace_prescription().execute(current_context(), rx_id=rx_id, body=draft)
        return jsonify(prescription_body(view))

    @bp.delete(one)
    @clinic(Permission.CLINICAL_WRITE)
    def discard_prescription(rx_id: UUID) -> tuple[str, int]:
        use_cases.discard_prescription().execute(current_context(), rx_id=rx_id)
        return "", 204

    @bp.post(f"{one}/issue")
    @clinic(Permission.CLINICAL_WRITE)
    def issue_prescription(rx_id: UUID) -> Response:
        body = parse_json(IssueRequest)
        view = use_cases.issue_prescription().execute(
            current_context(), rx_id=rx_id, seen_revision=body.revision
        )
        return jsonify(prescription_body(view))

    @bp.post(f"{one}/revise")
    @clinic(Permission.CLINICAL_WRITE)
    def revise_prescription(rx_id: UUID) -> tuple[Response, int]:
        view = use_cases.revise_prescription().execute(current_context(), rx_id=rx_id)
        return jsonify(prescription_body(view)), 201

    @bp.get(f"{one}/pdf")
    @clinic(Permission.RX_PRINT)
    def prescription_pdf(rx_id: UUID) -> Response:
        pdf = use_cases.download_prescription_pdf().execute(current_context(), rx_id=rx_id)
        response = Response(pdf.data, mimetype=PDF_CONTENT_TYPE)
        # Streamed to the authorised caller only; never cached, never a public or signed URL.
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Content-Disposition"] = f'inline; filename="{pdf.filename}"'
        return response

    @bp.get("/patients/<uuid:patient_id>/prescriptions")
    @clinic(Permission.RX_PRINT)
    def list_printable(patient_id: UUID) -> Response:
        rows = use_cases.list_printable().execute(current_context(), patient_id=patient_id)
        return jsonify(items_body(printable_body(r) for r in rows))

    return bp
