"""Payments and refunds (M6d-P3; ports/billing.py), tenant-scoped (ADR-0003)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date
from uuid import UUID

from mediease_api.adapters.db.models.billing import PaymentRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.billing.payment import Payment, PaymentKind, PaymentMode


def _payment(row: PaymentRow) -> Payment:
    return Payment(
        id=row.id,
        clinic_id=row.clinic_id,
        bill_id=row.bill_id,
        patient_id=row.patient_id,
        doctor_id=row.doctor_id,
        kind=PaymentKind(row.kind),
        mode=PaymentMode(row.mode),
        amount_paise=row.amount_paise,
        reference=row.reference,
        received_by=row.received_by,
        received_at=row.received_at.astimezone(UTC),
        local_date=row.local_date,
        voided_at=row.voided_at.astimezone(UTC) if row.voided_at else None,
        voided_by=row.voided_by,
        void_reason=row.void_reason,
    )


class SqlAlchemyPaymentRepository(TenantScopedRepository[PaymentRow]):
    model = PaymentRow
    entity_name = "payment"

    def add(self, payment: Payment) -> None:
        self._check_owned(payment.clinic_id)
        self._session.add(
            PaymentRow(
                id=payment.id,
                clinic_id=self.clinic_id,
                bill_id=payment.bill_id,
                patient_id=payment.patient_id,
                doctor_id=payment.doctor_id,
                kind=payment.kind.value,
                mode=payment.mode.value,
                amount_paise=payment.amount_paise,
                reference=payment.reference,
                received_by=payment.received_by,
                received_at=payment.received_at,
                local_date=payment.local_date,
            )
        )
        self._session.flush()

    def update(self, payment: Payment) -> None:
        """Only a void changes a payment (R35)."""
        self._check_owned(payment.clinic_id)
        row = self._require_row(payment.id)
        row.voided_at = payment.voided_at
        row.voided_by = payment.voided_by
        row.void_reason = payment.void_reason
        self._session.flush()

    def get(self, payment_id: UUID, *, for_update: bool = False) -> Payment | None:
        query = self._scoped_select().where(PaymentRow.id == payment_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _payment(row) if row else None

    def list_for_bill(self, bill_id: UUID) -> Sequence[Payment]:
        query = (
            self._scoped_select()
            .where(PaymentRow.bill_id == bill_id)
            .order_by(PaymentRow.received_at, PaymentRow.id)
        )
        return [_payment(row) for row in self._session.scalars(query)]

    def list_on(self, day: date) -> Sequence[Payment]:
        """Every payment and refund recorded on one clinic-local day, voided ones included."""
        query = (
            self._scoped_select()
            .where(PaymentRow.local_date == day)
            .order_by(PaymentRow.received_at, PaymentRow.id)
        )
        return [_payment(row) for row in self._session.scalars(query)]
