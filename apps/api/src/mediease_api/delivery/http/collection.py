"""The daily collection (M6d-P5; FR-BIL-06; spec billing R55-R62).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/clinic/collection?date`` | ``COLLECTION_VIEW`` |
| ``GET /api/v1/clinic/collection/export?date`` | ``COLLECTION_VIEW``; CSV, audited |
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, jsonify, request

from mediease_api.application.billing.collection import (
    CollectionDay,
    ExportCollection,
    GetCollection,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.audit_log import csv_safe
from mediease_api.delivery.http.bills import doctor_ref, patient_ref
from mediease_api.delivery.http.validation import RequestValidationFailed
from mediease_api.domain.billing.collection import Tally
from mediease_api.domain.identity.permissions import Permission

CSV_COLUMNS = (
    "Time",
    "Kind",
    "Mode",
    "Amount (Rs)",
    "Reference",
    "Bill",
    "Patient code",
    "Patient",
    "Doctor",
    "Taken by",
    "Voided",
)


class CollectionUseCases(Protocol):
    def get_collection(self) -> GetCollection: ...
    def export_collection(self) -> ExportCollection: ...


def _day() -> date | None:
    raw = request.args.get("date")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise RequestValidationFailed([{"field": "date", "reason": "must be YYYY-MM-DD"}]) from None


def _tally(t: Tally) -> dict[str, int]:
    return {
        "payments_paise": t.payments_paise,
        "refunds_paise": t.refunds_paise,
        "net_paise": t.net_paise,
        "count": t.count,
    }


def collection_body(day: CollectionDay) -> dict[str, Any]:
    s = day.summary
    return {
        "date": day.day.isoformat(),
        "timezone": day.timezone,
        "total": _tally(s.total),
        "voided": _tally(s.voided),
        "by_mode": [{"mode": mode.value, **_tally(t)} for mode, t in s.by_mode],
        "by_doctor": [
            {"doctor": doctor_ref(day.doctors.get(d) if d else None), **_tally(t)}
            for d, t in s.by_doctor
        ],
        "items": [
            {
                "id": str(p.id),
                "bill_id": str(p.bill_id),
                "bill_number": day.bills[p.bill_id].number if p.bill_id in day.bills else None,
                "kind": p.kind.value,
                "mode": p.mode.value,
                "amount_paise": p.amount_paise,
                "reference": p.reference,
                "received_at": p.received_at.isoformat(),
                "received_by": day.people.get(p.received_by),
                "patient": patient_ref(day.patients.get(p.patient_id)),
                "doctor": doctor_ref(day.doctors.get(p.doctor_id) if p.doctor_id else None),
                "voided": p.is_voided,
            }
            for p in day.payments
        ],
    }


def collection_csv(day: CollectionDay) -> str:
    zone = ZoneInfo(day.timezone)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for p in day.payments:
        patient = day.patients.get(p.patient_id)
        doctor = day.doctors.get(p.doctor_id) if p.doctor_id else None
        bill = day.bills.get(p.bill_id)
        writer.writerow(
            [
                csv_safe(cell)
                for cell in (
                    p.received_at.astimezone(zone).isoformat(timespec="seconds"),
                    p.kind.value,
                    p.mode.value,
                    f"{p.amount_paise / 100:.2f}",
                    p.reference or "",
                    (bill.number or "") if bill else "",
                    patient.code if patient else "",
                    patient.full_name if patient else "",
                    doctor.display_name if doctor else "",
                    day.people.get(p.received_by, ""),
                    "yes" if p.is_voided else "",
                )
            ]
        )
    return out.getvalue()


def create_collection_blueprint(use_cases: CollectionUseCases) -> Blueprint:
    bp = Blueprint("collection", __name__, url_prefix="/api/v1/clinic/collection")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.COLLECTION_VIEW)
    def get_collection() -> Response:
        return jsonify(
            collection_body(use_cases.get_collection().execute(current_context(), _day()))
        )

    @bp.get("/export")
    @clinic(Permission.COLLECTION_VIEW)
    def export_collection() -> Response:
        day = use_cases.export_collection().execute(current_context(), _day())
        name = f"collection-{day.clinic_slug}-{day.day.isoformat()}.csv"
        return Response(
            collection_csv(day),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    return bp
