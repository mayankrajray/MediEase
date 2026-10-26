"""Payments, refunds and dues (M6d-P3; FR-BIL-03, FR-BIL-05; spec billing R31-R42; B6, D2).

Recording and voiding need ``BILLING_MANAGE``; a doctor records them on their own bills only
(D2, R21). Each takes the bill row lock, so two payments on one bill cannot both fit a balance
meant for one. The dues list needs ``COLLECTION_VIEW`` (owners and the front desk).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.billing.bills import BillView, bill_view, load_bill
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.billing.payment import Payment, PaymentKind, PaymentMode
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.billing import PatientDues
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY = "payment"


@dataclass(frozen=True, slots=True)
class PaymentCommand:
    kind: PaymentKind
    mode: PaymentMode
    amount_paise: int
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class DuesView:
    items: tuple[PatientDues, ...]
    patients: Mapping[UUID, Patient]
    total_paise: int


class _UseCase:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids


class RecordPayment(_UseCase):
    """R31-R34: a payment up to the balance, or a refund up to what is owed back."""

    def execute(self, ctx: RequestContext, bill_id: UUID, cmd: PaymentCommand) -> BillView:
        with self._uow as uow:
            now = self._clock.now()
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id, for_update=True)
            payment = Payment.record(
                bill,
                id=self._ids.new_id(),
                kind=cmd.kind,
                mode=cmd.mode,
                amount_paise=cmd.amount_paise,
                reference=cmd.reference,
                by=ctx.user_id,
                now=now,
                today=local_date(now, clinic.timezone),
            )
            tenant.payments.add(payment)
            tenant.bills.update(bill)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.PAYMENT_RECORDED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY,
                entity_id=payment.id,
                metadata={
                    "bill_id": str(bill.id),
                    "kind": payment.kind.value,
                    "mode": payment.mode.value,
                    "amount_paise": str(payment.amount_paise),
                },
            )
            uow.commit()
            view = bill_view(uow, tenant, bill)
        logger.info(
            "payment.recorded",
            clinic_id=str(ctx.clinic_id),
            kind=payment.kind.value,
            mode=payment.mode.value,
            amount_paise=payment.amount_paise,
        )
        return view


class VoidPayment(_UseCase):
    """R35-R36: the same clinic-local day, with a reason; the bill takes the amount back."""

    def execute(
        self, ctx: RequestContext, bill_id: UUID, payment_id: UUID, *, reason: str
    ) -> BillView:
        with self._uow as uow:
            now = self._clock.now()
            clinic = load_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id, for_update=True)
            payment = tenant.payments.get(payment_id, for_update=True)
            if payment is None or payment.bill_id != bill.id:
                raise NotFound("payment")
            payment.void(
                bill, reason=reason, by=ctx.user_id, now=now, today=local_date(now, clinic.timezone)
            )
            tenant.payments.update(payment)
            tenant.bills.update(bill)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.PAYMENT_VOIDED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY,
                entity_id=payment.id,
                metadata={
                    "bill_id": str(bill.id),
                    "kind": payment.kind.value,
                    "amount_paise": str(payment.amount_paise),
                },
            )
            uow.commit()
            return bill_view(uow, tenant, bill)


class ListDues:
    """R39: patients who owe on issued bills, the largest first (200 at most)."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext, *, patient_id: UUID | None = None) -> DuesView:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            items = tuple(tenant.bills.dues(patient_id=patient_id))
            patients = {p.id: p for p in tenant.patients.get_many([d.patient_id for d in items])}
            return DuesView(items, patients, sum(d.due_paise for d in items))
