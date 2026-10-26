"""Bills and credit notes (M6d-P2; FR-BIL-02, FR-BIL-07; spec billing R13-R30; ADR-0022).

A bill is a **snapshot** (B3): each line copies the service name and price when it is drafted, so
a later fee change never alters it, and nothing clinical is ever copied from the visit. A bill is
``DRAFT`` while it is edited and ``ISSUED`` once numbered; an issued bill never changes (B4). It
is corrected only by a **credit note**, a document of its own (``kind`` ``CREDIT_NOTE``) that
reverses some or all of its lines, each line at most once. A fully credited bill is
``CANCELLED``.

Money is integer paise (B1). A line is ``unit price x quantity``, less its own discount; the
bill's discount is then shared across the lines in proportion to their value (largest remainder,
so the shares add up exactly), and each line's ``amount_paise`` is what it finally costs. A
credit note credits those amounts, so crediting every line gives back exactly the total.

Numbers (B5, D1) belong to the clinic and the Indian financial year (April to March) of the
clinic-local day of issue: ``<prefix>/26-27/0001`` for bills and ``<prefix>/CN/26-27/0001`` for
credit notes. The caller allocates the sequence under the clinic row lock, only at issue.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.billing.money import MAX_LINE_PAISE, check_price, percent_of
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.text import optional_text, required_text
from mediease_api.domain.shared.time import require_utc

MAX_LINES = 50
MAX_QUANTITY = 99
# B1: a bill up to ₹10,00,000.
MAX_BILL_PAISE = 10 * MAX_LINE_PAISE
DESCRIPTION_MAX = 80
NOTES_MAX = 500
REASON_MAX = 200
# A percentage in hundredths of a percent: 10000 is 100%.
MAX_PERCENT = 10_000


class BillKind(StrEnum):
    BILL = "BILL"
    CREDIT_NOTE = "CREDIT_NOTE"


class BillStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    # B4: every line credited. Only a bill, never a credit note.
    CANCELLED = "CANCELLED"


class DiscountKind(StrEnum):
    NONE = "NONE"
    AMOUNT = "AMOUNT"  # paise
    PERCENT = "PERCENT"  # hundredths of a percent


class BillNotDraft(DomainError):
    code = "BIL_NOT_DRAFT"

    def __init__(self) -> None:
        super().__init__("Only a draft bill can be changed, discarded or issued.")


class BillNotIssued(DomainError):
    code = "BIL_NOT_ISSUED"

    def __init__(self) -> None:
        super().__init__("Only an issued bill can be credited or paid.")


class BillEmpty(DomainError):
    code = "BIL_EMPTY"

    def __init__(self) -> None:
        super().__init__("Add at least one line before issuing the bill.")


class LineAlreadyCredited(DomainError):
    code = "BIL_LINE_ALREADY_CREDITED"

    def __init__(self) -> None:
        super().__init__("A chosen line has already been credited or is not on this bill.")


class VisitAlreadyBilled(DomainError):
    """R14: a visit has one open bill (a draft or an issued one); a cancelled one does not count."""

    code = "BIL_VISIT_BILLED"

    def __init__(self, bill_id: str | None = None) -> None:
        # The open bill's ID, so the screen can open it (it is the caller's clinic's).
        details = {"bill_id": bill_id} if bill_id else {}
        super().__init__("This visit already has a bill.", **details)


@dataclass(frozen=True, slots=True)
class Discount:
    kind: DiscountKind = DiscountKind.NONE
    value: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 0:
            raise InvalidValue("discount", "must be a whole, non-negative number")
        if self.kind is DiscountKind.NONE and self.value != 0:
            raise InvalidValue("discount", "must be 0 when there is no discount")
        if self.kind is DiscountKind.PERCENT and self.value > MAX_PERCENT:
            raise InvalidValue("discount", "must be at most 100%")

    def of(self, paise: int, field: str) -> int:
        """The discount on ``paise``; an amount larger than ``paise`` is refused."""
        if self.kind is DiscountKind.AMOUNT:
            if self.value > paise:
                raise InvalidValue(field, "must not be more than the amount")
            return self.value
        if self.kind is DiscountKind.PERCENT:
            return percent_of(paise, self.value)
        return 0


NO_DISCOUNT = Discount()


@dataclass(frozen=True, slots=True)
class LineInput:
    """A line as drafted: ``service_id`` names the fee schedule's service, if any."""

    description: str
    unit_price_paise: int
    quantity: int = 1
    discount: Discount = NO_DISCOUNT
    service_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class BillLine:
    id: UUID
    position: int
    service_id: UUID | None
    description: str
    unit_price_paise: int
    quantity: int
    discount: Discount
    # The line's own discount and its share of the bill's, both in paise.
    discount_paise: int
    bill_discount_paise: int
    # What the line finally costs: unit x quantity - discount_paise - bill_discount_paise.
    amount_paise: int
    # On a credit note: the bill line it reverses.
    credits_line_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class Priced:
    lines: tuple[BillLine, ...]
    subtotal_paise: int  # after line discounts
    discount_paise: int  # the bill's own discount
    total_paise: int


def price_lines(inputs: Sequence[LineInput], discount: Discount, ids: Iterable[UUID]) -> Priced:
    """R15-R17: each line's value, the bill discount shared exactly, and the totals."""
    if len(inputs) > MAX_LINES:
        raise InvalidValue("lines", f"at most {MAX_LINES}")
    new_ids = iter(ids)
    nets: list[tuple[LineInput, int, int]] = []
    for n, line in enumerate(inputs, start=1):
        field_ = f"lines.{n}"
        if isinstance(line.quantity, bool) or not 1 <= line.quantity <= MAX_QUANTITY:
            raise InvalidValue(f"{field_}.quantity", f"must be 1-{MAX_QUANTITY}")
        gross = check_price(line.unit_price_paise, f"{field_}.unit_price_paise") * line.quantity
        own = line.discount.of(gross, f"{field_}.discount")
        nets.append((line, own, gross - own))
    subtotal = sum(net for _, _, net in nets)
    bill_discount = discount.of(subtotal, "discount")
    shares = _share(bill_discount, [net for _, _, net in nets])
    total = subtotal - bill_discount
    if total > MAX_BILL_PAISE or subtotal > MAX_BILL_PAISE:
        raise InvalidValue("lines", f"a bill is at most {MAX_BILL_PAISE} paise")
    lines = tuple(
        BillLine(
            id=next(new_ids),
            position=n,
            service_id=line.service_id,
            description=required_text(
                line.description, f"lines.{n}.description", max_length=DESCRIPTION_MAX
            ),
            unit_price_paise=line.unit_price_paise,
            quantity=line.quantity,
            discount=line.discount,
            discount_paise=own,
            bill_discount_paise=share,
            amount_paise=net - share,
        )
        for n, ((line, own, net), share) in enumerate(zip(nets, shares, strict=True), start=1)
    )
    return Priced(lines, subtotal, bill_discount, total)


def _share(amount: int, weights: Sequence[int]) -> list[int]:
    """``amount`` split by ``weights``: floors, then the rest by the largest fraction, in order."""
    whole = sum(weights)
    if amount == 0 or whole == 0:
        return [0] * len(weights)
    floors = [amount * w // whole for w in weights]
    rest = amount - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % whole), i))
    for i in order[:rest]:
        floors[i] += 1
    return floors


def financial_year(day: date) -> str:
    """D1: the Indian financial year of ``day``, April to March: 2026-10-26 is ``26-27``."""
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def format_number(prefix: str, kind: BillKind, year: str, seq: int) -> str:
    """B5: ``SC/26-27/0001`` for a bill, ``SC/CN/26-27/0001`` for a credit note."""
    middle = "CN/" if kind is BillKind.CREDIT_NOTE else ""
    return f"{prefix}/{middle}{year}/{seq:04d}"


@dataclass(frozen=True, slots=True)
class Numbering:
    """A number allocated by the caller under the clinic row lock."""

    year: str
    seq: int
    number: str
    bill_date: date


@dataclass(slots=True)
class Bill:
    """A bill or a credit note. Build drafts with ``Bill.draft``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    kind: BillKind
    status: BillStatus
    patient_id: UUID
    visit_id: UUID | None
    doctor_id: UUID | None
    lines: tuple[BillLine, ...]
    discount: Discount
    subtotal_paise: int
    discount_paise: int
    total_paise: int
    notes: str | None
    number: str | None
    financial_year: str | None
    seq: int | None
    bill_date: date | None
    credits_bill_id: UUID | None
    reason: str | None
    # Kept up to date on the bill (credit notes in P2, payments and refunds in P3).
    credited_paise: int
    created_by: UUID
    issued_by: UUID | None
    issued_at: datetime | None
    created_at: datetime
    updated_at: datetime
    paid_paise: int = 0
    refunded_paise: int = 0
    # Line IDs already reversed by a credit note (bills only; loaded by the repository).
    credited_line_ids: frozenset[UUID] = field(default_factory=frozenset)

    @classmethod
    def draft(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        patient_id: UUID,
        visit_id: UUID | None,
        doctor_id: UUID | None,
        priced: Priced,
        discount: Discount,
        notes: str | None,
        by: UUID,
        now: datetime,
    ) -> Bill:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            kind=BillKind.BILL,
            status=BillStatus.DRAFT,
            patient_id=patient_id,
            visit_id=visit_id,
            doctor_id=doctor_id,
            lines=priced.lines,
            discount=discount,
            subtotal_paise=priced.subtotal_paise,
            discount_paise=priced.discount_paise,
            total_paise=priced.total_paise,
            notes=_notes(notes),
            number=None,
            financial_year=None,
            seq=None,
            bill_date=None,
            credits_bill_id=None,
            reason=None,
            credited_paise=0,
            created_by=by,
            issued_by=None,
            issued_at=None,
            created_at=now,
            updated_at=now,
        )

    def _require_draft(self) -> None:
        if self.status is not BillStatus.DRAFT:
            raise BillNotDraft()

    def change(
        self,
        *,
        priced: Priced,
        discount: Discount,
        notes: str | None,
        doctor_id: UUID | None,
        now: datetime,
    ) -> None:
        """R18: a draft's lines, discount, notes and doctor are replaced as a whole."""
        self._require_draft()
        self.lines = priced.lines
        self.discount = discount
        self.subtotal_paise = priced.subtotal_paise
        self.discount_paise = priced.discount_paise
        self.total_paise = priced.total_paise
        self.notes = _notes(notes)
        self.doctor_id = doctor_id
        self.updated_at = require_utc(now, "now")

    def check_discardable(self) -> None:
        self._require_draft()

    def issue(self, numbering: Numbering, *, by: UUID, now: datetime) -> None:
        """R20: numbered and frozen; an empty bill cannot be issued."""
        self._require_draft()
        if not self.lines:
            raise BillEmpty()
        self.status = BillStatus.ISSUED
        self.number = numbering.number
        self.financial_year = numbering.year
        self.seq = numbering.seq
        self.bill_date = numbering.bill_date
        self.issued_by = by
        self.issued_at = require_utc(now, "now")
        self.updated_at = self.issued_at

    @property
    def open_lines(self) -> tuple[BillLine, ...]:
        """The lines no credit note has reversed yet."""
        return tuple(line for line in self.lines if line.id not in self.credited_line_ids)

    @property
    def net_paise(self) -> int:
        """What the patient owes for the bill: its total less what was credited."""
        return self.total_paise - self.credited_paise

    @property
    def balance_paise(self) -> int:
        """B4 (P3): net, less payments, plus refunds. Negative: the clinic owes the patient."""
        return self.net_paise - self.paid_paise + self.refunded_paise

    def credit(
        self,
        *,
        id: UUID,
        line_ids: Sequence[UUID] | None,
        reason: str,
        numbering: Numbering,
        new_line_ids: Iterable[UUID],
        by: UUID,
        now: datetime,
    ) -> Bill:
        """R23-R26: a credit note reversing ``line_ids`` (all open lines when None).

        The bill records the credited amount and becomes ``CANCELLED`` when nothing is left.
        """
        if self.kind is not BillKind.BILL or self.status is not BillStatus.ISSUED:
            raise BillNotIssued()
        now = require_utc(now, "now")
        open_lines = {line.id: line for line in self.open_lines}
        if line_ids is None:
            chosen = list(open_lines.values())
        else:
            if not line_ids or len(set(line_ids)) != len(line_ids):
                raise InvalidValue("line_ids", "choose each line at most once")
            if any(i not in open_lines for i in line_ids):
                raise LineAlreadyCredited()
            chosen = [open_lines[i] for i in line_ids]
        if not chosen:
            raise LineAlreadyCredited()
        ids = iter(new_line_ids)
        lines = tuple(
            replace(line, id=next(ids), position=n, credits_line_id=line.id)
            for n, line in enumerate(sorted(chosen, key=lambda x: x.position), start=1)
        )
        amount = sum(line.amount_paise for line in lines)
        note = Bill(
            id=id,
            clinic_id=self.clinic_id,
            kind=BillKind.CREDIT_NOTE,
            status=BillStatus.ISSUED,
            patient_id=self.patient_id,
            visit_id=self.visit_id,
            doctor_id=self.doctor_id,
            lines=lines,
            discount=NO_DISCOUNT,
            subtotal_paise=amount,
            discount_paise=0,
            total_paise=amount,
            notes=None,
            number=numbering.number,
            financial_year=numbering.year,
            seq=numbering.seq,
            bill_date=numbering.bill_date,
            credits_bill_id=self.id,
            reason=required_text(reason, "reason", max_length=REASON_MAX),
            credited_paise=0,
            created_by=by,
            issued_by=by,
            issued_at=now,
            created_at=now,
            updated_at=now,
        )
        self.credited_paise += amount
        self.credited_line_ids = self.credited_line_ids | {line.id for line in chosen}
        if not self.open_lines:
            self.status = BillStatus.CANCELLED
        self.updated_at = now
        return note


def _notes(notes: str | None) -> str | None:
    return optional_text(notes, "notes", max_length=NOTES_MAX)
