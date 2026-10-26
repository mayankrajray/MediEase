"""Payments and refunds against a bill (M6d-P3; FR-BIL-03, FR-BIL-05; spec billing R31-R42).

A payment belongs to one issued bill and never takes more than its balance (B6). A refund gives
money back only when the bill is overpaid, which a credit note causes (balance below zero). Both
are recorded as they happen and never edited. A mistake is **voided** on the same clinic-local
day with a reason. After that day only a credit note and a refund correct it, so the day's
collection (P5) never changes once the day has closed. No advance or deposit is held.

The bill keeps ``paid_paise`` and ``refunded_paise``, so its balance is
``total - credited - paid + refunded`` (ADR-0022).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.billing.bill import (
    MAX_BILL_PAISE,
    Bill,
    BillKind,
    BillNotIssued,
    BillStatus,
)
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.text import optional_text, required_text
from mediease_api.domain.shared.time import require_utc

REFERENCE_MAX = 40
VOID_REASON_MAX = 200


class PaymentKind(StrEnum):
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"


class PaymentMode(StrEnum):
    CASH = "CASH"
    UPI = "UPI"
    CARD = "CARD"


class PaymentTooLarge(DomainError):
    """R32: a payment never exceeds the balance; a refund never exceeds what is owed back."""

    code = "BIL_PAYMENT_TOO_LARGE"

    def __init__(self, kind: PaymentKind, most: int) -> None:
        what = "payment" if kind is PaymentKind.PAYMENT else "refund"
        super().__init__(f"This {what} is more than the bill allows.", most_paise=str(most))


class VoidTooLate(DomainError):
    code = "BIL_VOID_TOO_LATE"

    def __init__(self) -> None:
        super().__init__(
            "A payment can be voided only on the day it was recorded; correct it with a credit"
            " note and a refund."
        )


class AlreadyVoided(DomainError):
    code = "BIL_ALREADY_VOIDED"

    def __init__(self) -> None:
        super().__init__("This payment is already voided.")


class VoidWouldUnbalance(DomainError):
    """R36: voiding a payment cannot leave more refunded than paid."""

    code = "BIL_VOID_REFUNDED"

    def __init__(self) -> None:
        super().__init__("Void the refund first: it was paid out of this payment.")


@dataclass(slots=True)
class Payment:
    id: UUID
    clinic_id: UUID
    bill_id: UUID
    patient_id: UUID
    doctor_id: UUID | None
    kind: PaymentKind
    mode: PaymentMode
    amount_paise: int
    reference: str | None
    received_by: UUID
    received_at: datetime
    # The clinic-local day it was recorded: the day of the collection it belongs to (P5).
    local_date: date
    voided_at: datetime | None = None
    voided_by: UUID | None = None
    void_reason: str | None = None

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    @classmethod
    def record(
        cls,
        bill: Bill,
        *,
        id: UUID,
        kind: PaymentKind,
        mode: PaymentMode,
        amount_paise: int,
        reference: str | None,
        by: UUID,
        now: datetime,
        today: date,
    ) -> Payment:
        """R31-R33: the payment or refund, applied to the bill's paid or refunded amount."""
        if bill.kind is not BillKind.BILL or bill.status is BillStatus.DRAFT:
            raise BillNotIssued()
        if isinstance(amount_paise, bool) or not 1 <= amount_paise <= MAX_BILL_PAISE:
            raise InvalidValue("amount_paise", f"must be 1 to {MAX_BILL_PAISE} paise")
        if kind is PaymentKind.PAYMENT:
            if bill.status is not BillStatus.ISSUED:
                raise BillNotIssued()
            most = max(bill.balance_paise, 0)
            if amount_paise > most:
                raise PaymentTooLarge(kind, most)
            bill.paid_paise += amount_paise
        else:
            most = max(-bill.balance_paise, 0)
            if amount_paise > most:
                raise PaymentTooLarge(kind, most)
            bill.refunded_paise += amount_paise
        now = require_utc(now, "now")
        bill.updated_at = now
        return cls(
            id=id,
            clinic_id=bill.clinic_id,
            bill_id=bill.id,
            patient_id=bill.patient_id,
            doctor_id=bill.doctor_id,
            kind=kind,
            mode=mode,
            amount_paise=amount_paise,
            reference=optional_text(reference, "reference", max_length=REFERENCE_MAX),
            received_by=by,
            received_at=now,
            local_date=today,
        )

    def void(self, bill: Bill, *, reason: str, by: UUID, now: datetime, today: date) -> None:
        """R35-R36: the same clinic-local day only, with a reason; the bill takes it back."""
        if self.is_voided:
            raise AlreadyVoided()
        if today != self.local_date:
            raise VoidTooLate()
        cleaned = required_text(reason, "reason", max_length=VOID_REASON_MAX)
        if self.kind is PaymentKind.PAYMENT:
            if bill.refunded_paise > bill.paid_paise - self.amount_paise:
                raise VoidWouldUnbalance()
            bill.paid_paise -= self.amount_paise
        else:
            bill.refunded_paise -= self.amount_paise
        now = require_utc(now, "now")
        bill.updated_at = now
        self.voided_at = now
        self.voided_by = by
        self.void_reason = cleaned
