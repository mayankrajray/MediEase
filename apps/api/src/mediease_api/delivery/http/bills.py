"""Bills and credit notes (M6d-P2; FR-BIL-02, FR-BIL-07; spec billing R13-R30).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/clinic/bills?patient_id&doctor_id&status&cursor`` | ``BILLING_MANAGE`` |
| ``POST /api/v1/clinic/bills`` | ``BILLING_MANAGE`` |
| ``GET /api/v1/clinic/bills/{bill_id}`` | ``BILLING_MANAGE`` |
| ``PUT /api/v1/clinic/bills/{bill_id}`` (a draft) | ``BILLING_MANAGE`` |
| ``DELETE /api/v1/clinic/bills/{bill_id}`` (a draft) | ``BILLING_MANAGE`` |
| ``POST /api/v1/clinic/bills/{bill_id}/issue`` | ``BILLING_MANAGE`` |
| ``POST /api/v1/clinic/bills/{bill_id}/credit-notes`` | ``BILLING_MANAGE`` |
| ``POST /api/v1/clinic/bills/{bill_id}/payments`` (M6d-P3) | ``BILLING_MANAGE`` |
| ``POST /api/v1/clinic/bills/{bill_id}/payments/{payment_id}/void`` | ``BILLING_MANAGE`` |
| ``GET /api/v1/clinic/dues?patient_id`` (M6d-P3) | ``COLLECTION_VIEW`` |

A doctor reaches only their own bills (R21; another's is 404). Amounts are paise.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict, Field

from mediease_api.application.billing.bills import (
    BillCommand,
    BillPage,
    BillView,
    ChangeBill,
    CreditBill,
    DiscardBill,
    DraftBill,
    GetBill,
    IssueBill,
    LineCommand,
    ListBills,
)
from mediease_api.application.billing.payments import (
    DuesView,
    ListDues,
    PaymentCommand,
    RecordPayment,
    VoidPayment,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.scheduling import _uuid_arg
from mediease_api.delivery.http.validation import RequestValidationFailed, parse_json
from mediease_api.domain.billing.bill import (
    DESCRIPTION_MAX,
    MAX_LINES,
    MAX_QUANTITY,
    NOTES_MAX,
    REASON_MAX,
    Bill,
    BillLine,
    BillStatus,
    Discount,
    DiscountKind,
)
from mediease_api.domain.billing.money import MAX_LINE_PAISE
from mediease_api.domain.billing.payment import (
    REFERENCE_MAX,
    VOID_REASON_MAX,
    Payment,
    PaymentKind,
    PaymentMode,
)
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.patients.patient import Patient
from mediease_api.ports.billing import BillCursor, BillQuery


class DiscountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: DiscountKind
    # AMOUNT in paise; PERCENT in hundredths of a percent (1250 = 12.5%).
    value: int = Field(ge=0, le=10 * MAX_LINE_PAISE)

    def domain(self) -> Discount:
        return Discount(self.kind, self.value)


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: UUID | None = None
    description: str | None = Field(default=None, min_length=1, max_length=DESCRIPTION_MAX)
    unit_price_paise: int | None = Field(default=None, ge=0, le=MAX_LINE_PAISE)
    quantity: int = Field(default=1, ge=1, le=MAX_QUANTITY)
    discount: DiscountIn | None = None

    def command(self) -> LineCommand:
        return LineCommand(
            service_id=self.service_id,
            description=self.description,
            unit_price_paise=self.unit_price_paise,
            quantity=self.quantity,
            discount=self.discount.domain() if self.discount else Discount(),
        )


class _Content(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discount: DiscountIn | None = None
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class NewBillIn(_Content):
    patient_id: UUID
    visit_id: UUID | None = None
    doctor_id: UUID | None = None
    # Left out with a visit: the doctor's consultation, prefilled (R15).
    lines: list[LineIn] | None = Field(default=None, max_length=MAX_LINES)


class BillChangeIn(_Content):
    lines: list[LineIn] = Field(max_length=MAX_LINES)
    doctor_id: UUID | None = None


class CreditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Left out or null: every line not yet credited (cancels the bill).
    line_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=MAX_LINES)
    reason: str = Field(min_length=1, max_length=REASON_MAX)


class PaymentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PaymentKind = PaymentKind.PAYMENT
    mode: PaymentMode
    amount_paise: int = Field(ge=1, le=10 * MAX_LINE_PAISE)
    # A UPI or card reference; never needed for cash.
    reference: str | None = Field(default=None, max_length=REFERENCE_MAX)


class VoidIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=VOID_REASON_MAX)


class BillUseCases(Protocol):
    def list_bills(self) -> ListBills: ...
    def draft_bill(self) -> DraftBill: ...
    def get_bill(self) -> GetBill: ...
    def change_bill(self) -> ChangeBill: ...
    def discard_bill(self) -> DiscardBill: ...
    def issue_bill(self) -> IssueBill: ...
    def credit_bill(self) -> CreditBill: ...
    def record_payment(self) -> RecordPayment: ...
    def void_payment(self) -> VoidPayment: ...
    def list_dues(self) -> ListDues: ...


def _command(body: _Content, lines: list[LineIn]) -> BillCommand:
    return BillCommand(
        lines=[line.command() for line in lines],
        discount=body.discount.domain() if body.discount else Discount(),
        notes=body.notes,
    )


def patient_ref(patient: Patient | None) -> dict[str, Any] | None:
    if patient is None:
        return None
    return {"id": str(patient.id), "code": patient.code, "full_name": patient.full_name}


def doctor_ref(doctor: Doctor | None) -> dict[str, Any] | None:
    return None if doctor is None else {"id": str(doctor.id), "display_name": doctor.display_name}


def _discount(discount: Discount) -> dict[str, Any]:
    return {"kind": discount.kind.value, "value": discount.value}


def _line_body(line: BillLine, credited: frozenset[UUID]) -> dict[str, Any]:
    return {
        "id": str(line.id),
        "position": line.position,
        "service_id": str(line.service_id) if line.service_id else None,
        "description": line.description,
        "unit_price_paise": line.unit_price_paise,
        "quantity": line.quantity,
        "discount": _discount(line.discount),
        "discount_paise": line.discount_paise,
        "bill_discount_paise": line.bill_discount_paise,
        "amount_paise": line.amount_paise,
        "credited": line.id in credited,
    }


def _when(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def summary_body(bill: Bill, patient: Patient | None, doctor: Doctor | None) -> dict[str, Any]:
    return {
        "id": str(bill.id),
        "status": bill.status.value,
        "number": bill.number,
        "bill_date": bill.bill_date.isoformat() if bill.bill_date else None,
        "patient": patient_ref(patient),
        "doctor": doctor_ref(doctor),
        "visit_id": str(bill.visit_id) if bill.visit_id else None,
        "total_paise": bill.total_paise,
        "credited_paise": bill.credited_paise,
        "paid_paise": bill.paid_paise,
        "refunded_paise": bill.refunded_paise,
        "balance_paise": bill.balance_paise if bill.status is not BillStatus.DRAFT else None,
        "created_at": bill.created_at.isoformat(),
        "issued_at": _when(bill.issued_at),
    }


def payment_body(payment: Payment, people: Mapping[UUID, str]) -> dict[str, Any]:
    return {
        "id": str(payment.id),
        "kind": payment.kind.value,
        "mode": payment.mode.value,
        "amount_paise": payment.amount_paise,
        "reference": payment.reference,
        "received_at": payment.received_at.isoformat(),
        "local_date": payment.local_date.isoformat(),
        "received_by": people.get(payment.received_by),
        "voided_at": _when(payment.voided_at),
        "voided_by": people.get(payment.voided_by) if payment.voided_by else None,
        "void_reason": payment.void_reason,
    }


def bill_body(view: BillView) -> dict[str, Any]:
    bill = view.bill
    return {
        **summary_body(bill, view.patient, view.doctor),
        "lines": [_line_body(line, bill.credited_line_ids) for line in bill.lines],
        "discount": _discount(bill.discount),
        "subtotal_paise": bill.subtotal_paise,
        "discount_paise": bill.discount_paise,
        "notes": bill.notes,
        "updated_at": bill.updated_at.isoformat(),
        "credit_notes": [
            {
                "id": str(note.id),
                "number": note.number,
                "bill_date": note.bill_date.isoformat() if note.bill_date else None,
                "reason": note.reason,
                "total_paise": note.total_paise,
                "issued_at": _when(note.issued_at),
                "lines": [
                    {
                        "id": str(line.id),
                        "credits_line_id": str(line.credits_line_id),
                        "description": line.description,
                        "amount_paise": line.amount_paise,
                    }
                    for line in note.lines
                ],
            }
            for note in view.credit_notes
        ],
        "payments": [payment_body(p, view.people) for p in view.payments],
    }


def page_body(page: BillPage) -> dict[str, Any]:
    return {
        "items": [
            summary_body(
                b,
                page.patients.get(b.patient_id),
                page.doctors.get(b.doctor_id) if b.doctor_id else None,
            )
            for b in page.items
        ],
        "next_cursor": _encode(page.next_cursor) if page.next_cursor else None,
    }


def _encode(cursor: BillCursor) -> str:
    raw = f"{cursor.created_at.isoformat()}|{cursor.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _cursor() -> BillCursor | None:
    raw = request.args.get("cursor")
    if not raw:
        return None
    try:
        text = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        when, ident = text.split("|", 1)
        created = datetime.fromisoformat(when)
        if created.tzinfo is None:
            raise ValueError("naive")
        return BillCursor(created, UUID(ident))
    except (ValueError, UnicodeDecodeError):
        raise RequestValidationFailed(
            [{"field": "cursor", "reason": "is not a cursor from this list"}]
        ) from None


def _status() -> BillStatus | None:
    raw = request.args.get("status")
    if not raw:
        return None
    try:
        return BillStatus(raw)
    except ValueError:
        raise RequestValidationFailed(
            [{"field": "status", "reason": "must be DRAFT, ISSUED or CANCELLED"}]
        ) from None


def create_bills_blueprint(use_cases: BillUseCases) -> Blueprint:
    bp = Blueprint("bills", __name__, url_prefix="/api/v1/clinic/bills")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.BILLING_MANAGE)
    def list_bills() -> Response:
        page = use_cases.list_bills().execute(
            current_context(),
            BillQuery(
                patient_id=_uuid_arg("patient_id"),
                doctor_id=_uuid_arg("doctor_id"),
                status=_status(),
                after=_cursor(),
            ),
        )
        return jsonify(page_body(page))

    @bp.post("")
    @clinic(Permission.BILLING_MANAGE)
    def draft_bill() -> tuple[Response, int]:
        body = parse_json(NewBillIn)
        view = use_cases.draft_bill().execute(
            current_context(),
            patient_id=body.patient_id,
            visit_id=body.visit_id,
            doctor_id=body.doctor_id,
            command=_command(body, body.lines) if body.lines is not None else None,
        )
        return jsonify(bill_body(view)), 201

    @bp.get("/<uuid:bill_id>")
    @clinic(Permission.BILLING_MANAGE)
    def get_bill(bill_id: UUID) -> Response:
        return jsonify(bill_body(use_cases.get_bill().execute(current_context(), bill_id)))

    @bp.put("/<uuid:bill_id>")
    @clinic(Permission.BILLING_MANAGE)
    def change_bill(bill_id: UUID) -> Response:
        body = parse_json(BillChangeIn)
        view = use_cases.change_bill().execute(
            current_context(),
            bill_id,
            _command(body, body.lines),
            doctor_id=body.doctor_id,
            doctor_given="doctor_id" in body.model_fields_set,
        )
        return jsonify(bill_body(view))

    @bp.delete("/<uuid:bill_id>")
    @clinic(Permission.BILLING_MANAGE)
    def discard_bill(bill_id: UUID) -> tuple[str, int]:
        use_cases.discard_bill().execute(current_context(), bill_id)
        return "", 204

    @bp.post("/<uuid:bill_id>/issue")
    @clinic(Permission.BILLING_MANAGE)
    def issue_bill(bill_id: UUID) -> Response:
        return jsonify(bill_body(use_cases.issue_bill().execute(current_context(), bill_id)))

    @bp.post("/<uuid:bill_id>/credit-notes")
    @clinic(Permission.BILLING_MANAGE)
    def credit_bill(bill_id: UUID) -> tuple[Response, int]:
        body = parse_json(CreditIn)
        view = use_cases.credit_bill().execute(
            current_context(), bill_id, line_ids=body.line_ids, reason=body.reason
        )
        return jsonify(bill_body(view)), 201

    @bp.post("/<uuid:bill_id>/payments")
    @clinic(Permission.BILLING_MANAGE)
    def record_payment(bill_id: UUID) -> tuple[Response, int]:
        body = parse_json(PaymentIn)
        view = use_cases.record_payment().execute(
            current_context(),
            bill_id,
            PaymentCommand(body.kind, body.mode, body.amount_paise, body.reference),
        )
        return jsonify(bill_body(view)), 201

    @bp.post("/<uuid:bill_id>/payments/<uuid:payment_id>/void")
    @clinic(Permission.BILLING_MANAGE)
    def void_payment(bill_id: UUID, payment_id: UUID) -> Response:
        body = parse_json(VoidIn)
        view = use_cases.void_payment().execute(
            current_context(), bill_id, payment_id, reason=body.reason
        )
        return jsonify(bill_body(view))

    return bp


def dues_body(view: DuesView) -> dict[str, Any]:
    return {
        "total_paise": view.total_paise,
        "items": [
            {
                "patient": patient_ref(view.patients.get(d.patient_id)),
                "bills": d.bills,
                "due_paise": d.due_paise,
                "oldest_bill_date": d.oldest_bill_date.isoformat(),
            }
            for d in view.items
        ],
    }


def create_dues_blueprint(use_cases: BillUseCases) -> Blueprint:
    """M6d-P3 (R39): who owes the clinic, for owners and the front desk."""
    bp = Blueprint("dues", __name__, url_prefix="/api/v1/clinic/dues")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.COLLECTION_VIEW)
    def list_dues() -> Response:
        view = use_cases.list_dues().execute(current_context(), patient_id=_uuid_arg("patient_id"))
        return jsonify(dues_body(view))

    return bp
