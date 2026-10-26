"""The printed bill (M6d-P4; spec billing R43-R47)."""

from __future__ import annotations

from datetime import date

import pytest

from mediease_api.domain.billing.bill import (
    Bill,
    Discount,
    DiscountKind,
    LineInput,
    Numbering,
    price_lines,
)
from mediease_api.domain.billing.payment import Payment, PaymentKind, PaymentMode
from mediease_api.domain.billing.receipt import (
    ReceiptNotReady,
    build_receipt,
    format_rupees,
    receipt_object_key,
    receipt_state,
)
from tests.builders import LATER, NOW, a_clinic, a_doctor, a_patient, new_id

TODAY = date(2026, 10, 26)


def test_r47_rupees_in_indian_grouping() -> None:
    assert format_rupees(0) == "₹0.00"
    assert format_rupees(5) == "₹0.05"
    assert format_rupees(100000) == "₹1,000.00"
    assert format_rupees(12345678) == "₹1,23,456.78"
    assert format_rupees(100_000_000) == "₹10,00,000.00"
    assert format_rupees(-2500) == "\N{MINUS SIGN}₹25.00"


def _bill(clinic_id, patient_id, doctor_id):  # type: ignore[no-untyped-def]
    bill = Bill.draft(
        id=new_id(),
        clinic_id=clinic_id,
        patient_id=patient_id,
        visit_id=None,
        doctor_id=doctor_id,
        priced=price_lines(
            [
                LineInput("Consultation", 50000),
                LineInput("Dressing", 20000, discount=Discount(DiscountKind.PERCENT, 1000)),
            ],
            Discount(DiscountKind.AMOUNT, 1000),
            [new_id(), new_id()],
        ),
        discount=Discount(DiscountKind.AMOUNT, 1000),
        notes="Paid at the desk",
        by=new_id(),
        now=NOW,
    )
    return bill


def test_r43_r47_the_document_shows_the_bill_as_it_stands() -> None:
    clinic = a_clinic(address_line="12 Sample Road", city="Pune")
    doctor = a_doctor(clinic.id)
    patient = a_patient(clinic.id, new_id())
    bill = _bill(clinic.id, patient.id, doctor.id)
    with pytest.raises(ReceiptNotReady):
        build_receipt(
            bill, credit_notes=[], payments=[], patient=patient, doctor=doctor, clinic=clinic
        )
    bill.issue(Numbering("26-27", 1, "SC/26-27/0001", TODAY), by=new_id(), now=NOW)
    note = bill.credit(
        id=new_id(),
        line_ids=[bill.lines[1].id],
        reason="Not done",
        numbering=Numbering("26-27", 1, "SC/CN/26-27/0001", TODAY),
        new_line_ids=[new_id()],
        by=new_id(),
        now=LATER,
    )
    pay = Payment.record(
        bill,
        id=new_id(),
        kind=PaymentKind.PAYMENT,
        mode=PaymentMode.UPI,
        amount_paise=10000,
        reference="UPI-1",
        by=new_id(),
        now=LATER,
        today=TODAY,
    )
    pay.void(bill, reason="Wrong", by=new_id(), now=LATER, today=TODAY)
    doc = build_receipt(
        bill, credit_notes=[note], payments=[pay], patient=patient, doctor=doctor, clinic=clinic
    )

    assert (doc.number, doc.bill_date, doc.doctor_name, doc.clinic_name) == (
        "SC/26-27/0001",
        "26 Oct 2026",
        doctor.display_name,
        clinic.name,
    )
    assert doc.clinic_lines[0] == "12 Sample Road"
    assert [(line.description, line.credited) for line in doc.lines] == [
        ("Consultation", False),
        ("Dressing", True),
    ]
    assert [t.label for t in doc.totals] == ["Subtotal", "Bill discount", "Total", "Credited"]
    assert (
        doc.payments[0].struck
        and "voided" in doc.payments[0].label
        and "UPI-1" in doc.payments[0].label
    )
    assert doc.credit_notes[0].label.startswith("Credit note SC/CN/26-27/0001")
    assert doc.balance.label == "Balance due" and doc.notes == "Paid at the desk"
    assert {e.value for e in doc.patient} == {patient.full_name, patient.code}


def test_r45_the_state_moves_with_every_change_after_issue() -> None:
    clinic_id, bill_id = new_id(), new_id()
    assert receipt_state([], []) == 0
    assert receipt_object_key(clinic_id, bill_id, 3) == f"receipt/{clinic_id}/{bill_id}/s3.pdf"
