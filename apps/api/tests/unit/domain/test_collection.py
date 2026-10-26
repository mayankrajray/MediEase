"""The day's sums (M6d-P5; spec billing R56-R58)."""

from __future__ import annotations

from datetime import date

from mediease_api.domain.billing.collection import summarise
from mediease_api.domain.billing.payment import Payment, PaymentKind, PaymentMode
from tests.builders import NOW, new_id

DAY = date(2026, 10, 26)
DOC_A, DOC_B = new_id(), new_id()


def _p(amount: int, mode: PaymentMode, doctor, kind=PaymentKind.PAYMENT, voided=False):  # type: ignore[no-untyped-def]
    return Payment(
        id=new_id(),
        clinic_id=new_id(),
        bill_id=new_id(),
        patient_id=new_id(),
        doctor_id=doctor,
        kind=kind,
        mode=mode,
        amount_paise=amount,
        reference=None,
        received_by=new_id(),
        received_at=NOW,
        local_date=DAY,
        voided_at=NOW if voided else None,
        voided_by=new_id() if voided else None,
        void_reason="x" if voided else None,
    )


def test_r56_r58_totals_by_mode_and_doctor_without_the_voided() -> None:
    s = summarise(
        [
            _p(50000, PaymentMode.CASH, DOC_A),
            _p(30000, PaymentMode.UPI, DOC_B),
            _p(20000, PaymentMode.CASH, DOC_A, PaymentKind.REFUND),
            _p(9900, PaymentMode.CARD, None, voided=True),
            _p(100, PaymentMode.CARD, None),
        ]
    )
    assert (s.total.payments_paise, s.total.refunds_paise, s.total.net_paise, s.total.count) == (
        80100,
        20000,
        60100,
        4,
    )
    assert (s.voided.count, s.voided.payments_paise) == (1, 9900)
    assert {m.value: t.net_paise for m, t in s.by_mode} == {
        "CASH": 30000,
        "UPI": 30000,
        "CARD": 100,
    }
    nets = [t.net_paise for _, t in s.by_doctor]
    assert nets == sorted(nets, reverse=True)
    assert {d: t.net_paise for d, t in s.by_doctor} == {DOC_A: 30000, DOC_B: 30000, None: 100}
    assert sum(t.net_paise for _, t in s.by_doctor) == s.total.net_paise


def test_an_empty_day_has_every_mode_at_zero() -> None:
    s = summarise([])
    assert s.total.net_paise == 0 and s.by_doctor == ()
    assert [m.value for m, _ in s.by_mode] == ["CASH", "UPI", "CARD"]
