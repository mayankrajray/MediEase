"""Bills and credit notes (M6d-P2; FR-BIL-02, FR-BIL-07; spec billing R13-R30; ADR-0022).

Every role holds ``BILLING_MANAGE`` (B2), but a **doctor** works only on their own bills: those
with their doctor profile (R21). Owners and the front desk see every bill. A bill never holds
clinical content (B3): the visit gives only its patient and doctor, and the lines come from the
fee schedule or are typed.

Lock order (R27): the clinic row, then the bill row. Issuing and crediting take both, because
they allocate a number (B5); editing a draft takes the bill row only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.billing.fees import load_schedule
from mediease_api.application.context import Actor, RequestContext
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.billing.bill import (
    NO_DISCOUNT,
    Bill,
    BillKind,
    Discount,
    LineInput,
    Numbering,
    VisitAlreadyBilled,
    financial_year,
    format_number,
    price_lines,
)
from mediease_api.domain.billing.fees import ClinicService, consultation_service
from mediease_api.domain.billing.payment import Payment
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.shared.errors import DomainError, InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.domain.visits.visit import VisitStatus
from mediease_api.ports.billing import BillCursor, BillQuery
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY = "bill"
PAGE_SIZE = 50


class BillNotYours(DomainError):
    """R21: a doctor bills only for themselves."""

    code = "BIL_NOT_YOURS"

    def __init__(self) -> None:
        super().__init__("Doctors can bill only their own consultations.")


class VisitNotCompletedForBill(DomainError):
    code = "BIL_VISIT_NOT_COMPLETED"

    def __init__(self) -> None:
        super().__init__("Bill a visit once the consultation is completed.")


@dataclass(frozen=True, slots=True)
class LineCommand:
    """A line as sent. With ``service_id``, a missing description or price comes from the fee
    schedule (the service's name; the bill doctor's price)."""

    service_id: UUID | None = None
    description: str | None = None
    unit_price_paise: int | None = None
    quantity: int = 1
    discount: Discount = NO_DISCOUNT


@dataclass(frozen=True, slots=True)
class BillCommand:
    lines: Sequence[LineCommand]
    discount: Discount = NO_DISCOUNT
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class BillView:
    bill: Bill
    credit_notes: tuple[Bill, ...]
    patient: Patient
    doctor: Doctor | None
    # M6d-P3: payments and refunds, oldest first, and the names of who took or voided them.
    payments: tuple[Payment, ...] = ()
    people: Mapping[UUID, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BillPage:
    items: tuple[Bill, ...]
    patients: Mapping[UUID, Patient]
    doctors: Mapping[UUID, Doctor]
    next_cursor: BillCursor | None


def own_doctor_id(tenant: TenantRepositories, ctx: RequestContext) -> UUID | None:
    """R21: a doctor's own profile; None for the roles that see every bill."""
    if ctx.role is not Role.DOCTOR:
        return None
    doctor = tenant.doctors.get_for_user(ctx.user_id)
    if doctor is None or not doctor.is_active:
        raise BillNotYours()
    return doctor.id


def load_bill(
    tenant: TenantRepositories, ctx: RequestContext, bill_id: UUID, *, for_update: bool = False
) -> Bill:
    """The bill, or not found: another clinic's, a credit note, or another doctor's (R21)."""
    bill = tenant.bills.get(bill_id, for_update=for_update)
    own = own_doctor_id(tenant, ctx)
    if (
        bill is None
        or bill.kind is not BillKind.BILL
        or (own is not None and bill.doctor_id != own)
    ):
        raise NotFound("bill")
    return bill


def bill_view(uow: UnitOfWork, tenant: TenantRepositories, bill: Bill) -> BillView:
    patient = tenant.patients.get(bill.patient_id)
    assert patient is not None  # a foreign key
    doctor = tenant.doctors.get(bill.doctor_id) if bill.doctor_id else None
    payments = tuple(tenant.payments.list_for_bill(bill.id))
    people: dict[UUID, str] = {}
    for user_id in {p.received_by for p in payments} | {
        p.voided_by for p in payments if p.voided_by is not None
    }:
        user = uow.users.get(user_id)
        if user is not None:
            people[user_id] = user.full_name
    return BillView(
        bill,
        tuple(tenant.bills.credit_notes_for(bill.id)),
        patient,
        doctor,
        payments,
        people,
    )


def _lines(
    tenant: TenantRepositories, commands: Sequence[LineCommand], doctor_id: UUID | None
) -> list[LineInput]:
    """R16: each line's description and price, filled from the fee schedule where left out."""
    schedule = load_schedule(tenant) if any(c.service_id for c in commands) else None
    services: dict[UUID, ClinicService] = (
        {s.id: s for s in schedule.services} if schedule is not None else {}
    )
    lines: list[LineInput] = []
    for n, cmd in enumerate(commands, start=1):
        description, price = cmd.description, cmd.unit_price_paise
        if cmd.service_id is not None:
            service = services.get(cmd.service_id)
            if service is None or not service.active:
                raise InvalidValue(f"lines.{n}.service_id", "is not an active service")
            assert schedule is not None
            description = description or service.name
            if price is None:
                price = schedule.price(service, doctor_id)
        if description is None:
            raise InvalidValue(f"lines.{n}.description", "is required without a service")
        if price is None:
            raise InvalidValue(f"lines.{n}.unit_price_paise", "the service has no price: enter one")
        lines.append(LineInput(description, price, cmd.quantity, cmd.discount, cmd.service_id))
    return lines


def _audit(
    uow: UnitOfWork,
    ids: IdPort,
    ctx: RequestContext,
    action: AuditAction,
    bill: Bill,
    now: datetime,
    **metadata: str,
) -> None:
    record_event(
        uow,
        event_id=ids.new_id(),
        action=action,
        actor=Actor.staff(ctx),
        now=now,
        clinic_id=ctx.clinic_id,
        entity_type=ENTITY,
        entity_id=bill.id,
        metadata={"total_paise": str(bill.total_paise), **metadata},
    )


def _locked_clinic(uow: UnitOfWork, clinic_id: UUID) -> Clinic:
    clinic = uow.clinics.get(clinic_id, for_update=True)
    if clinic is None:  # pragma: no cover - the request context names a live clinic
        raise NotFound("clinic")
    return clinic


def _numbering(
    tenant: TenantRepositories, clinic: Clinic, kind: BillKind, now: datetime
) -> Numbering:
    """B5: the next number of the series, under the clinic row lock the caller holds."""
    day = local_date(now, clinic.timezone)
    year = financial_year(day)
    seq = tenant.bills.next_seq(kind, year)
    return Numbering(year, seq, format_number(clinic.patient_code_prefix, kind, year, seq), day)


class _UseCase:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids


class DraftBill(_UseCase):
    """R13-R16: a draft for a patient, from their completed visit or on its own."""

    def execute(
        self,
        ctx: RequestContext,
        *,
        patient_id: UUID,
        visit_id: UUID | None,
        doctor_id: UUID | None,
        command: BillCommand | None,
    ) -> BillView:
        with self._uow as uow:
            now = self._clock.now()
            tenant = uow.tenant(ctx.clinic_id)
            own = own_doctor_id(tenant, ctx)
            if tenant.patients.get(patient_id) is None:
                raise NotFound("patient")
            if visit_id is not None:
                visit = tenant.visits.get(visit_id)
                if visit is None:
                    raise NotFound("visit")
                if visit.patient_id != patient_id:
                    raise InvalidValue("visit_id", "is not this patient's visit")
                if visit.status is not VisitStatus.COMPLETED:
                    raise VisitNotCompletedForBill()
                if doctor_id is not None and doctor_id != visit.doctor_id:
                    raise InvalidValue("doctor_id", "a visit's bill is for the visit's doctor")
                doctor_id = visit.doctor_id
                existing = tenant.bills.open_for_visit(visit_id)
                if existing is not None:
                    raise VisitAlreadyBilled(str(existing.id))
            if own is not None:
                if doctor_id is not None and doctor_id != own:
                    raise BillNotYours()
                doctor_id = own
            if doctor_id is not None and tenant.doctors.get(doctor_id) is None:
                raise NotFound("doctor")
            if command is None:
                command = BillCommand(lines=self._prefill(tenant, visit_id, doctor_id))
            priced = price_lines(
                _lines(tenant, command.lines, doctor_id),
                command.discount,
                (self._ids.new_id() for _ in command.lines),
            )
            bill = Bill.draft(
                id=self._ids.new_id(),
                clinic_id=ctx.clinic_id,
                patient_id=patient_id,
                visit_id=visit_id,
                doctor_id=doctor_id,
                priced=priced,
                discount=command.discount,
                notes=command.notes,
                by=ctx.user_id,
                now=now,
            )
            tenant.bills.add(bill)
            _audit(
                uow,
                self._ids,
                ctx,
                AuditAction.BILL_DRAFTED,
                bill,
                now,
                visit="true" if visit_id else "false",
                lines=str(len(bill.lines)),
            )
            uow.commit()
            view = bill_view(uow, tenant, bill)
        logger.info("bill.drafted", clinic_id=str(ctx.clinic_id), from_visit=visit_id is not None)
        return view

    @staticmethod
    def _prefill(
        tenant: TenantRepositories, visit_id: UUID | None, doctor_id: UUID | None
    ) -> list[LineCommand]:
        """R15: a visit's bill starts with the consultation at the doctor's price, if priced."""
        if visit_id is None:
            return []
        schedule = load_schedule(tenant)
        service = consultation_service(schedule.services)
        if service is None or schedule.price(service, doctor_id) is None:
            return []
        return [LineCommand(service_id=service.id)]


class ChangeBill(_UseCase):
    """R18: a draft's lines, discount and notes, replaced as a whole."""

    def execute(
        self,
        ctx: RequestContext,
        bill_id: UUID,
        command: BillCommand,
        *,
        doctor_id: UUID | None,
        doctor_given: bool,
    ) -> BillView:
        with self._uow as uow:
            now = self._clock.now()
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id, for_update=True)
            new_doctor = bill.doctor_id
            if doctor_given and doctor_id != bill.doctor_id:
                # A visit's bill and a doctor's own bill keep their doctor.
                if bill.visit_id is not None or own_doctor_id(tenant, ctx) is not None:
                    raise InvalidValue("doctor_id", "this bill's doctor cannot change")
                if doctor_id is not None and tenant.doctors.get(doctor_id) is None:
                    raise NotFound("doctor")
                new_doctor = doctor_id
            priced = price_lines(
                _lines(tenant, command.lines, new_doctor),
                command.discount,
                (self._ids.new_id() for _ in command.lines),
            )
            bill.change(
                priced=priced,
                discount=command.discount,
                notes=command.notes,
                doctor_id=new_doctor,
                now=now,
            )
            tenant.bills.update(bill)
            _audit(
                uow,
                self._ids,
                ctx,
                AuditAction.BILL_CHANGED,
                bill,
                now,
                lines=str(len(bill.lines)),
            )
            uow.commit()
            return bill_view(uow, tenant, bill)


class DiscardBill(_UseCase):
    """R19: a draft is deleted; it never had a number."""

    def execute(self, ctx: RequestContext, bill_id: UUID) -> None:
        with self._uow as uow:
            now = self._clock.now()
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id, for_update=True)
            bill.check_discardable()
            tenant.bills.delete_draft(bill.id)
            _audit(uow, self._ids, ctx, AuditAction.BILL_DISCARDED, bill, now)
            uow.commit()


class IssueBill(_UseCase):
    """R20: the next number of the financial year, and the bill is frozen."""

    def execute(self, ctx: RequestContext, bill_id: UUID) -> BillView:
        with self._uow as uow:
            now = self._clock.now()
            clinic = _locked_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id, for_update=True)
            bill.issue(_numbering(tenant, clinic, BillKind.BILL, now), by=ctx.user_id, now=now)
            tenant.bills.update(bill)
            assert bill.number is not None
            _audit(uow, self._ids, ctx, AuditAction.BILL_ISSUED, bill, now, number=bill.number)
            uow.commit()
            view = bill_view(uow, tenant, bill)
        logger.info("bill.issued", clinic_id=str(ctx.clinic_id), total_paise=bill.total_paise)
        return view


class CreditBill(_UseCase):
    """R23-R26: a numbered credit note for some or all of the open lines."""

    def execute(
        self, ctx: RequestContext, bill_id: UUID, *, line_ids: Sequence[UUID] | None, reason: str
    ) -> BillView:
        with self._uow as uow:
            now = self._clock.now()
            clinic = _locked_clinic(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            bill = load_bill(tenant, ctx, bill_id, for_update=True)
            note = bill.credit(
                id=self._ids.new_id(),
                line_ids=line_ids,
                reason=reason,
                numbering=_numbering(tenant, clinic, BillKind.CREDIT_NOTE, now),
                new_line_ids=(self._ids.new_id() for _ in bill.lines),
                by=ctx.user_id,
                now=now,
            )
            tenant.bills.add(note)
            tenant.bills.update(bill)
            assert note.number is not None
            _audit(
                uow,
                self._ids,
                ctx,
                AuditAction.BILL_CREDITED,
                bill,
                now,
                credit_note_id=str(note.id),
                number=note.number,
                amount_paise=str(note.total_paise),
                lines=str(len(note.lines)),
                status=bill.status.value,
            )
            uow.commit()
            view = bill_view(uow, tenant, bill)
        logger.info("bill.credited", clinic_id=str(ctx.clinic_id), amount_paise=note.total_paise)
        return view


class GetBill:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext, bill_id: UUID) -> BillView:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            return bill_view(uow, tenant, load_bill(tenant, ctx, bill_id))


class ListBills:
    """R22: newest first, 50 at a time; a doctor sees only their own."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext, query: BillQuery) -> BillPage:
        with self._uow as uow:
            tenant = uow.tenant(ctx.clinic_id)
            own = own_doctor_id(tenant, ctx)
            if own is not None:
                if query.doctor_id is not None and query.doctor_id != own:
                    raise BillNotYours()
                query = BillQuery(
                    patient_id=query.patient_id,
                    doctor_id=own,
                    status=query.status,
                    after=query.after,
                    limit=query.limit,
                )
            items = tuple(
                tenant.bills.list(
                    BillQuery(
                        patient_id=query.patient_id,
                        doctor_id=query.doctor_id,
                        status=query.status,
                        after=query.after,
                        limit=PAGE_SIZE + 1,
                    )
                )
            )
            more = len(items) > PAGE_SIZE
            items = items[:PAGE_SIZE]
            patients = {p.id: p for p in tenant.patients.get_many({b.patient_id for b in items})}
            doctors = {d.id: d for d in tenant.doctors.list()}
            last = items[-1] if more else None
            return BillPage(
                items,
                patients,
                doctors,
                BillCursor(last.created_at, last.id) if last is not None else None,
            )
