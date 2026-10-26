"""Bills and credit notes (M6d-P2; ports/billing.py), tenant-scoped (ADR-0003).

Lines are written with the bill: a draft's are replaced on every save, an issued bill's never
change. ``bill_lines`` is reached only through ``SqlAlchemyBillRepository`` (as the prices are
through the fee repository), by its own tenant-scoped repository.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import UTC
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediease_api.adapters.db.models.billing import BillLineRow, BillRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.billing.bill import (
    Bill,
    BillKind,
    BillLine,
    BillStatus,
    Discount,
    DiscountKind,
    VisitAlreadyBilled,
)
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.billing import BillQuery, PatientDues

_VISIT_INDEX = "uq_bills_visit_id"


def _line(row: BillLineRow) -> BillLine:
    return BillLine(
        id=row.id,
        position=row.position,
        service_id=row.service_id,
        description=row.description,
        unit_price_paise=row.unit_price_paise,
        quantity=row.quantity,
        discount=Discount(DiscountKind(row.discount_kind), row.discount_value),
        discount_paise=row.discount_paise,
        bill_discount_paise=row.bill_discount_paise,
        amount_paise=row.amount_paise,
        credits_line_id=row.credits_line_id,
    )


def _bill(row: BillRow, lines: Sequence[BillLine] = (), credited: Collection[UUID] = ()) -> Bill:
    return Bill(
        id=row.id,
        clinic_id=row.clinic_id,
        kind=BillKind(row.kind),
        status=BillStatus(row.status),
        patient_id=row.patient_id,
        visit_id=row.visit_id,
        doctor_id=row.doctor_id,
        lines=tuple(lines),
        discount=Discount(DiscountKind(row.discount_kind), row.discount_value),
        subtotal_paise=row.subtotal_paise,
        discount_paise=row.discount_paise,
        total_paise=row.total_paise,
        notes=row.notes,
        number=row.number,
        financial_year=row.financial_year,
        seq=row.seq,
        bill_date=row.bill_date,
        credits_bill_id=row.credits_bill_id,
        reason=row.reason,
        credited_paise=row.credited_paise,
        created_by=row.created_by,
        issued_by=row.issued_by,
        issued_at=row.issued_at.astimezone(UTC) if row.issued_at else None,
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
        paid_paise=row.paid_paise,
        refunded_paise=row.refunded_paise,
        credited_line_ids=frozenset(credited),
    )


def _write(row: BillRow, bill: Bill) -> None:
    row.kind = bill.kind.value
    row.status = bill.status.value
    row.patient_id = bill.patient_id
    row.visit_id = bill.visit_id
    row.doctor_id = bill.doctor_id
    row.discount_kind = bill.discount.kind.value
    row.discount_value = bill.discount.value
    row.subtotal_paise = bill.subtotal_paise
    row.discount_paise = bill.discount_paise
    row.total_paise = bill.total_paise
    row.credited_paise = bill.credited_paise
    row.paid_paise = bill.paid_paise
    row.refunded_paise = bill.refunded_paise
    row.notes = bill.notes
    row.number = bill.number
    row.financial_year = bill.financial_year
    row.seq = bill.seq
    row.bill_date = bill.bill_date
    row.credits_bill_id = bill.credits_bill_id
    row.reason = bill.reason
    row.created_by = bill.created_by
    row.issued_by = bill.issued_by
    row.issued_at = bill.issued_at
    row.updated_at = bill.updated_at


class SqlAlchemyBillLineRepository(TenantScopedRepository[BillLineRow]):
    """``bill_lines`` of one clinic; reached through ``SqlAlchemyBillRepository``."""

    model = BillLineRow
    entity_name = "bill line"

    def for_bills(self, bill_ids: Collection[UUID]) -> dict[UUID, list[BillLine]]:
        if not bill_ids:
            return {}
        query = (
            self._scoped_select()
            .where(BillLineRow.bill_id.in_(bill_ids))
            .order_by(BillLineRow.bill_id, BillLineRow.position)
        )
        found: dict[UUID, list[BillLine]] = defaultdict(list)
        for row in self._session.scalars(query):
            found[row.bill_id].append(_line(row))
        return found

    def credited_among(self, line_ids: Collection[UUID]) -> set[UUID]:
        """Which of these lines a credit-note line already reverses."""
        if not line_ids:
            return set()
        query = select(BillLineRow.credits_line_id).where(
            BillLineRow.clinic_id == self.clinic_id, BillLineRow.credits_line_id.in_(line_ids)
        )
        return {i for i in self._session.scalars(query) if i is not None}

    def insert(self, bill: Bill) -> None:
        for line in bill.lines:
            self._session.add(
                BillLineRow(
                    id=line.id,
                    clinic_id=self.clinic_id,
                    bill_id=bill.id,
                    position=line.position,
                    service_id=line.service_id,
                    description=line.description,
                    unit_price_paise=line.unit_price_paise,
                    quantity=line.quantity,
                    discount_kind=line.discount.kind.value,
                    discount_value=line.discount.value,
                    discount_paise=line.discount_paise,
                    bill_discount_paise=line.bill_discount_paise,
                    amount_paise=line.amount_paise,
                    credits_line_id=line.credits_line_id,
                )
            )

    def delete_for(self, bill_id: UUID) -> None:
        self._session.execute(
            delete(BillLineRow).where(
                BillLineRow.clinic_id == self.clinic_id, BillLineRow.bill_id == bill_id
            )
        )


class SqlAlchemyBillRepository(TenantScopedRepository[BillRow]):
    model = BillRow
    entity_name = "bill"

    def __init__(self, session: Session, clinic_id: UUID) -> None:
        super().__init__(session, clinic_id)
        self._lines = SqlAlchemyBillLineRepository(session, clinic_id)

    def add(self, bill: Bill) -> None:
        self._check_owned(bill.clinic_id)
        row = BillRow(id=bill.id, clinic_id=self.clinic_id, created_at=bill.created_at)
        _write(row, bill)
        self._session.add(row)
        self._flush()
        self._lines.insert(bill)
        self._session.flush()

    def update(self, bill: Bill) -> None:
        self._check_owned(bill.clinic_id)
        row = self._require_row(bill.id)
        was_draft = row.status == BillStatus.DRAFT.value
        _write(row, bill)
        if was_draft:
            # R18: a draft's lines are replaced as a whole (and frozen once issued).
            self._lines.delete_for(bill.id)
            self._session.flush()
            self._lines.insert(bill)
        self._flush()

    def _flush(self) -> None:
        try:
            with self._session.begin_nested():
                self._session.flush()
        except IntegrityError as error:
            if _VISIT_INDEX in str(error.orig):
                raise VisitAlreadyBilled() from None
            raise

    def _load(self, rows: Sequence[BillRow]) -> list[Bill]:
        lines = self._lines.for_bills([r.id for r in rows])
        bill_line_ids = [
            line.id for r in rows if r.kind == BillKind.BILL.value for line in lines.get(r.id, [])
        ]
        credited = self._lines.credited_among(bill_line_ids)
        return [
            _bill(
                r,
                lines.get(r.id, []),
                {line.id for line in lines.get(r.id, []) if line.id in credited},
            )
            for r in rows
        ]

    def get(self, bill_id: UUID, *, for_update: bool = False) -> Bill | None:
        query = self._scoped_select().where(BillRow.id == bill_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return self._load([row])[0] if row else None

    def delete_draft(self, bill_id: UUID) -> None:
        row = self._require_row(bill_id)
        if row.status != BillStatus.DRAFT.value:  # pragma: no cover - the use case checks first
            raise NotFound(self.entity_name)
        self._lines.delete_for(bill_id)
        self._delete_row(bill_id)

    def get_many(self, bill_ids: Collection[UUID]) -> Sequence[Bill]:
        if not bill_ids:
            return []
        query = self._scoped_select().where(BillRow.id.in_(bill_ids))
        return [_bill(row) for row in self._session.scalars(query)]

    def open_for_visit(self, visit_id: UUID) -> Bill | None:
        query = self._scoped_select().where(
            BillRow.visit_id == visit_id,
            BillRow.kind == BillKind.BILL.value,
            BillRow.status != BillStatus.CANCELLED.value,
        )
        row = self._session.scalars(query).one_or_none()
        return _bill(row) if row else None

    def credit_notes_for(self, bill_id: UUID) -> Sequence[Bill]:
        query = (
            self._scoped_select()
            .where(BillRow.credits_bill_id == bill_id)
            .order_by(BillRow.created_at, BillRow.id)
        )
        return self._load(list(self._session.scalars(query)))

    def next_seq(self, kind: BillKind, financial_year: str) -> int:
        query = select(func.coalesce(func.max(BillRow.seq), 0)).where(
            BillRow.clinic_id == self.clinic_id,
            BillRow.kind == kind.value,
            BillRow.financial_year == financial_year,
        )
        return int(self._session.scalar(query) or 0) + 1

    def list(self, query: BillQuery) -> Sequence[Bill]:
        stmt = self._scoped_select().where(BillRow.kind == BillKind.BILL.value)
        if query.patient_id is not None:
            stmt = stmt.where(BillRow.patient_id == query.patient_id)
        if query.doctor_id is not None:
            stmt = stmt.where(BillRow.doctor_id == query.doctor_id)
        if query.status is not None:
            stmt = stmt.where(BillRow.status == query.status.value)
        if query.after is not None:
            stmt = stmt.where(
                or_(
                    BillRow.created_at < query.after.created_at,
                    tuple_(BillRow.created_at, BillRow.id)
                    < tuple_(query.after.created_at, query.after.id),
                )
            )
        stmt = stmt.order_by(BillRow.created_at.desc(), BillRow.id.desc()).limit(query.limit)
        return [_bill(row) for row in self._session.scalars(stmt)]

    def _owing(self) -> tuple[ColumnElement[int], tuple[ColumnElement[bool], ...]]:
        balance = (
            BillRow.total_paise
            - BillRow.credited_paise
            - BillRow.paid_paise
            + BillRow.refunded_paise
        )
        return balance, (
            BillRow.clinic_id == self.clinic_id,
            BillRow.kind == BillKind.BILL.value,
            BillRow.status == BillStatus.ISSUED.value,
            balance > 0,
        )

    def dues(self, *, patient_id: UUID | None = None, limit: int = 200) -> Sequence[PatientDues]:
        balance, where = self._owing()
        due = func.sum(balance)
        query = select(BillRow.patient_id, func.count(), due, func.min(BillRow.bill_date)).where(
            *where
        )
        if patient_id is not None:
            query = query.where(BillRow.patient_id == patient_id)
        query = query.group_by(BillRow.patient_id).order_by(due.desc(), BillRow.patient_id)
        return [
            # Issued bills always have a bill date (CHECK numbered_when_issued).
            PatientDues(row[0], int(row[1]), int(row[2]), row[3])  # type: ignore[arg-type]
            for row in self._session.execute(query.limit(limit))
        ]

    def dues_for(self, patient_ids: Sequence[UUID]) -> dict[UUID, int]:
        if not patient_ids:
            return {}
        balance, where = self._owing()
        query = (
            select(BillRow.patient_id, func.sum(balance))
            .where(*where, BillRow.patient_id.in_(patient_ids))
            .group_by(BillRow.patient_id)
        )
        return {row[0]: int(row[1]) for row in self._session.execute(query)}
