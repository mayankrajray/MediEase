"""Payments and refunds in the domain (M6d-P3; spec billing R31-R36; B6)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from mediease_api.domain.billing.bill import (
    NO_DISCOUNT,
    Bill,
    BillNotIssued,
    LineInput,
    Numbering,
    price_lines,
)
from mediease_api.domain.billing.payment import (
    AlreadyVoided,
    Payment,
    PaymentKind,
    PaymentMode,
    PaymentTooLarge,
    VoidTooLate,
    VoidWouldUnbalance,
)
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import LATER, NOW, new_id

TODAY = date(2026, 10, 26)


def _issued(*amounts: int) -> Bill:
    priced = price_lines(
        [LineInput(f"Line {n}", a) for n, a in enumerate(amounts)],
        NO_DISCOUNT,
        [new_id() for _ in amounts],
    )
    bill = Bill.draft(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        visit_id=None,
        doctor_id=new_id(),
        priced=priced,
        discount=NO_DISCOUNT,
        notes=None,
        by=new_id(),
        now=NOW,
    )
    bill.issue(Numbering("26-27", 1, "SC/26-27/0001", TODAY), by=new_id(), now=NOW)
    return bill


def _pay(
    bill: Bill,
    amount: int,
    kind: PaymentKind = PaymentKind.PAYMENT,
    mode: PaymentMode = PaymentMode.CASH,
) -> Payment:
    return Payment.record(
        bill,
        id=new_id(),
        kind=kind,
        mode=mode,
        amount_paise=amount,
        reference=" UPI-123 ",
        by=new_id(),
        now=LATER,
        today=TODAY,
    )


def test_r31_r32_payments_up_to_the_balance_and_never_more() -> None:
    bill = _issued(50000)
    first = _pay(bill, 20000)
    assert (
        first.reference,
        first.local_date,
        first.patient_id,
        bill.paid_paise,
        bill.balance_paise,
    ) == (
        "UPI-123",
        TODAY,
        bill.patient_id,
        20000,
        30000,
    )
    with pytest.raises(PaymentTooLarge) as too_much:
        _pay(bill, 30001)
    assert too_much.value.details == {"most_paise": "30000"}
    _pay(bill, 30000, mode=PaymentMode.UPI)
    assert bill.balance_paise == 0
    with pytest.raises(PaymentTooLarge):
        _pay(bill, 1)
    with pytest.raises(InvalidValue):
        _pay(bill, 0)


def test_r33_a_refund_only_when_a_credit_note_leaves_the_bill_overpaid() -> None:
    bill = _issued(30000, 20000)
    _pay(bill, 50000)
    with pytest.raises(PaymentTooLarge):
        _pay(bill, 1, PaymentKind.REFUND)
    bill.credit(
        id=new_id(),
        line_ids=[bill.lines[1].id],
        reason="Not done",
        numbering=Numbering("26-27", 1, "SC/CN/26-27/0001", TODAY),
        new_line_ids=[new_id()],
        by=new_id(),
        now=LATER,
    )
    assert bill.balance_paise == -20000
    with pytest.raises(PaymentTooLarge):
        _pay(bill, 20001, PaymentKind.REFUND)
    _pay(bill, 20000, PaymentKind.REFUND)
    assert (bill.refunded_paise, bill.balance_paise) == (20000, 0)


def test_r31_a_cancelled_bill_takes_refunds_only_and_a_draft_nothing() -> None:
    bill = _issued(10000)
    _pay(bill, 10000)
    bill.credit(
        id=new_id(),
        line_ids=None,
        reason="Wrong patient",
        numbering=Numbering("26-27", 2, "SC/CN/26-27/0002", TODAY),
        new_line_ids=[new_id()],
        by=new_id(),
        now=LATER,
    )
    with pytest.raises(BillNotIssued):
        _pay(bill, 1)
    _pay(bill, 10000, PaymentKind.REFUND)
    draft = Bill.draft(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        visit_id=None,
        doctor_id=None,
        priced=price_lines([LineInput("A", 100)], NO_DISCOUNT, [new_id()]),
        discount=NO_DISCOUNT,
        notes=None,
        by=new_id(),
        now=NOW,
    )
    with pytest.raises(BillNotIssued):
        _pay(draft, 100)


def test_r35_a_void_on_the_same_day_with_a_reason_gives_the_amount_back() -> None:
    bill = _issued(50000)
    payment = _pay(bill, 50000)
    with pytest.raises(VoidTooLate):
        payment.void(bill, reason="Wrong", by=new_id(), now=LATER, today=TODAY + timedelta(days=1))
    with pytest.raises(InvalidValue):
        payment.void(bill, reason=" ", by=new_id(), now=LATER, today=TODAY)
    payment.void(bill, reason=" Wrong amount ", by=new_id(), now=LATER, today=TODAY)
    assert (payment.is_voided, payment.void_reason, bill.paid_paise, bill.balance_paise) == (
        True,
        "Wrong amount",
        0,
        50000,
    )
    with pytest.raises(AlreadyVoided):
        payment.void(bill, reason="Again", by=new_id(), now=LATER, today=TODAY)


def test_r36_a_payment_a_refund_came_out_of_is_voided_after_the_refund() -> None:
    bill = _issued(30000, 20000)
    payment = _pay(bill, 50000)
    bill.credit(
        id=new_id(),
        line_ids=[bill.lines[1].id],
        reason="Not done",
        numbering=Numbering("26-27", 1, "SC/CN/26-27/0001", TODAY),
        new_line_ids=[new_id()],
        by=new_id(),
        now=LATER,
    )
    refund = _pay(bill, 20000, PaymentKind.REFUND)
    with pytest.raises(VoidWouldUnbalance):
        payment.void(bill, reason="Wrong", by=new_id(), now=LATER, today=TODAY)
    refund.void(bill, reason="Not paid out", by=new_id(), now=LATER, today=TODAY)
    payment.void(bill, reason="Wrong", by=new_id(), now=LATER, today=TODAY)
    assert (bill.paid_paise, bill.refunded_paise, bill.balance_paise) == (0, 0, 30000)
