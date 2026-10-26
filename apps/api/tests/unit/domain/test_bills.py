"""Bills and credit notes in the domain (M6d-P2; spec billing R13-R30; ADR-0022)."""

from __future__ import annotations

from datetime import date

import pytest

from mediease_api.domain.billing.bill import (
    MAX_BILL_PAISE,
    NO_DISCOUNT,
    Bill,
    BillEmpty,
    BillKind,
    BillNotDraft,
    BillNotIssued,
    BillStatus,
    Discount,
    DiscountKind,
    LineAlreadyCredited,
    LineInput,
    Numbering,
    financial_year,
    format_number,
    price_lines,
)
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import LATER, NOW, new_id


def _ids(n: int = 60) -> list:  # type: ignore[type-arg]
    return [new_id() for _ in range(n)]


def _draft(lines: list[LineInput], discount: Discount = NO_DISCOUNT) -> Bill:
    return Bill.draft(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        visit_id=None,
        doctor_id=new_id(),
        priced=price_lines(lines, discount, _ids()),
        discount=discount,
        notes=" paid at the desk ",
        by=new_id(),
        now=NOW,
    )


NUMBER = Numbering("26-27", 1, "SC/26-27/0001", date(2026, 10, 26))
CN = Numbering("26-27", 1, "SC/CN/26-27/0001", date(2026, 10, 26))


def test_r16_lines_line_discounts_and_the_bill_discount_add_up_exactly() -> None:
    priced = price_lines(
        [
            LineInput("Consultation", 50000),
            LineInput("Dressing", 15000, quantity=2, discount=Discount(DiscountKind.AMOUNT, 5000)),
            LineInput("Injection", 10001, discount=Discount(DiscountKind.PERCENT, 1250)),
        ],
        Discount(DiscountKind.PERCENT, 1000),
        _ids(),
    )
    # 50000 + (30000 - 5000) + (10001 - 1250 half up) = 50000 + 25000 + 8751
    assert priced.subtotal_paise == 83751
    assert priced.discount_paise == 8375  # 10% of 83751, half up
    assert priced.total_paise == 75376
    assert sum(line.amount_paise for line in priced.lines) == priced.total_paise
    assert sum(line.bill_discount_paise for line in priced.lines) == priced.discount_paise
    for line in priced.lines:
        gross = line.unit_price_paise * line.quantity
        assert line.amount_paise == gross - line.discount_paise - line.bill_discount_paise
    assert [line.position for line in priced.lines] == [1, 2, 3]


def test_r16_the_bill_discount_is_shared_by_largest_remainder() -> None:
    priced = price_lines(
        [LineInput("A", 100), LineInput("B", 100), LineInput("C", 100)],
        Discount(DiscountKind.AMOUNT, 100),
        _ids(),
    )
    assert [line.bill_discount_paise for line in priced.lines] == [34, 33, 33]
    assert priced.total_paise == 200


def test_r17_discounts_and_limits_are_refused_with_the_field() -> None:
    with pytest.raises(InvalidValue) as too_much:
        price_lines(
            [LineInput("A", 100, discount=Discount(DiscountKind.AMOUNT, 101))], NO_DISCOUNT, _ids()
        )
    assert too_much.value.field == "lines.1.discount"
    with pytest.raises(InvalidValue):
        Discount(DiscountKind.PERCENT, 10_001)
    with pytest.raises(InvalidValue):
        Discount(DiscountKind.NONE, 5)
    with pytest.raises(InvalidValue) as bill_discount:
        price_lines([LineInput("A", 100)], Discount(DiscountKind.AMOUNT, 101), _ids())
    assert bill_discount.value.field == "discount"
    with pytest.raises(InvalidValue):
        price_lines([LineInput("A", 100, quantity=0)], NO_DISCOUNT, _ids())
    with pytest.raises(InvalidValue):
        price_lines([LineInput("A", 10_000_001)], NO_DISCOUNT, _ids())
    with pytest.raises(InvalidValue):
        price_lines([LineInput(" ", 100)], NO_DISCOUNT, _ids())
    eleven_lakh = [LineInput("A", 10_000_000, quantity=11)]
    with pytest.raises(InvalidValue):
        price_lines(eleven_lakh, NO_DISCOUNT, _ids())
    ten_lakh = price_lines([LineInput("A", 10_000_000, quantity=10)], NO_DISCOUNT, _ids())
    assert ten_lakh.total_paise == MAX_BILL_PAISE


def test_d1_b5_financial_years_and_numbers() -> None:
    assert financial_year(date(2026, 3, 31)) == "25-26"
    assert financial_year(date(2026, 4, 1)) == "26-27"
    assert financial_year(date(2099, 12, 1)) == "99-00"
    assert format_number("SC", BillKind.BILL, "26-27", 7) == "SC/26-27/0007"
    assert format_number("SC", BillKind.CREDIT_NOTE, "26-27", 12345) == "SC/CN/26-27/12345"


def test_r18_r20_a_draft_changes_until_issued_and_then_never() -> None:
    bill = _draft([LineInput("Consultation", 50000)])
    assert (bill.status, bill.number, bill.notes) == (BillStatus.DRAFT, None, "paid at the desk")
    bill.change(
        priced=price_lines([LineInput("Follow-up", 30000)], NO_DISCOUNT, _ids()),
        discount=NO_DISCOUNT,
        notes=None,
        doctor_id=bill.doctor_id,
        now=LATER,
    )
    assert bill.total_paise == 30000 and bill.updated_at == LATER
    bill.issue(NUMBER, by=new_id(), now=LATER)
    assert (bill.status, bill.number, bill.financial_year, bill.seq) == (
        BillStatus.ISSUED,
        "SC/26-27/0001",
        "26-27",
        1,
    )
    with pytest.raises(BillNotDraft):
        bill.change(
            priced=price_lines([], NO_DISCOUNT, []),
            discount=NO_DISCOUNT,
            notes=None,
            doctor_id=None,
            now=LATER,
        )
    with pytest.raises(BillNotDraft):
        bill.issue(NUMBER, by=new_id(), now=LATER)
    with pytest.raises(BillNotDraft):
        bill.check_discardable()


def test_r20_an_empty_draft_cannot_be_issued() -> None:
    with pytest.raises(BillEmpty):
        _draft([]).issue(NUMBER, by=new_id(), now=LATER)


def test_r23_r26_credit_notes_reverse_lines_once_and_cancel_the_bill_at_the_end() -> None:
    bill = _draft(
        [LineInput("A", 30000), LineInput("B", 20001), LineInput("C", 10000)],
        Discount(DiscountKind.PERCENT, 333),
    )
    with pytest.raises(BillNotIssued):
        bill.credit(
            id=new_id(),
            line_ids=None,
            reason="x",
            numbering=CN,
            new_line_ids=_ids(),
            by=new_id(),
            now=LATER,
        )
    bill.issue(NUMBER, by=new_id(), now=LATER)
    first, second, third = bill.lines

    note = bill.credit(
        id=new_id(),
        line_ids=[second.id],
        reason=" Wrong service ",
        numbering=CN,
        new_line_ids=_ids(),
        by=new_id(),
        now=LATER,
    )
    assert (note.kind, note.status, note.credits_bill_id, note.reason) == (
        BillKind.CREDIT_NOTE,
        BillStatus.ISSUED,
        bill.id,
        "Wrong service",
    )
    assert [line.credits_line_id for line in note.lines] == [second.id]
    assert note.total_paise == second.amount_paise == bill.credited_paise
    assert bill.status is BillStatus.ISSUED
    assert bill.open_lines == (first, third)

    with pytest.raises(LineAlreadyCredited):
        bill.credit(
            id=new_id(),
            line_ids=[second.id],
            reason="again",
            numbering=CN,
            new_line_ids=_ids(),
            by=new_id(),
            now=LATER,
        )
    with pytest.raises(InvalidValue):
        bill.credit(
            id=new_id(),
            line_ids=[first.id, first.id],
            reason="dup",
            numbering=CN,
            new_line_ids=_ids(),
            by=new_id(),
            now=LATER,
        )

    rest = bill.credit(
        id=new_id(),
        line_ids=None,
        reason="Cancelled visit",
        numbering=CN,
        new_line_ids=_ids(),
        by=new_id(),
        now=LATER,
    )
    assert [line.credits_line_id for line in rest.lines] == [first.id, third.id]
    # Crediting every line gives back exactly the total.
    assert bill.credited_paise == bill.total_paise and bill.net_paise == 0
    assert bill.status is BillStatus.CANCELLED
    with pytest.raises(BillNotIssued):
        bill.credit(
            id=new_id(),
            line_ids=None,
            reason="x",
            numbering=CN,
            new_line_ids=_ids(),
            by=new_id(),
            now=LATER,
        )


def test_b4_the_balance_counts_credits_payments_and_refunds() -> None:
    bill = _draft([LineInput("A", 50000)])
    bill.issue(NUMBER, by=new_id(), now=LATER)
    bill.paid_paise, bill.refunded_paise = 30000, 5000
    assert bill.balance_paise == 50000 - 30000 + 5000
