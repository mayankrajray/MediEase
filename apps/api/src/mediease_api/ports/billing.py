"""Billing repositories (M6d), each tenant-scoped (ADR-0003)."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.billing.bill import Bill, BillKind, BillStatus
from mediease_api.domain.billing.fees import ClinicService, DoctorPrice
from mediease_api.domain.billing.payment import Payment


class FeeRepository(Protocol):
    """``clinic_services`` and ``doctor_service_prices`` of one clinic (M6d-P1)."""

    def list_services(self) -> Sequence[ClinicService]:
        """Every service, active and retired, in the schedule's order."""
        ...

    def get_service(
        self, service_id: UUID, *, for_update: bool = False
    ) -> ClinicService | None: ...

    def add_service(self, service: ClinicService) -> None:
        """Insert; another active service with the name is ``BIL_SERVICE_NAME_TAKEN``."""
        ...

    def update_service(self, service: ClinicService) -> None:
        """Save; another active service with the name is ``BIL_SERVICE_NAME_TAKEN``."""
        ...

    def list_prices(self) -> Sequence[DoctorPrice]: ...

    def set_price(
        self, service_id: UUID, doctor_id: UUID, price_paise: int | None, *, id: UUID, now: datetime
    ) -> None:
        """The doctor's own price for the service; ``None`` removes it (the default applies)."""
        ...


@dataclass(frozen=True, slots=True)
class BillCursor:
    """Keyset position in a newest-first list of bills."""

    created_at: datetime
    id: UUID


@dataclass(frozen=True, slots=True)
class BillQuery:
    patient_id: UUID | None = None
    doctor_id: UUID | None = None
    status: BillStatus | None = None
    after: BillCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class PatientDues:
    """What one patient owes across their issued bills (P3, R39)."""

    patient_id: UUID
    bills: int
    due_paise: int
    oldest_bill_date: date


class BillRepository(Protocol):
    """``bills`` and ``bill_lines`` of one clinic (M6d-P2)."""

    def add(self, bill: Bill) -> None:
        """Insert a bill or a credit note with its lines; a second open bill for the visit is
        ``BIL_VISIT_BILLED``."""
        ...

    def update(self, bill: Bill) -> None:
        """Save the header; a draft's lines are replaced, an issued bill's never change."""
        ...

    def get(self, bill_id: UUID, *, for_update: bool = False) -> Bill | None:
        """The bill with its lines and, for a bill, which lines credit notes reversed."""
        ...

    def delete_draft(self, bill_id: UUID) -> None: ...

    def get_many(self, bill_ids: Collection[UUID]) -> Sequence[Bill]:
        """These bills of this clinic, without their lines (P5); others are skipped."""
        ...

    def open_for_visit(self, visit_id: UUID) -> Bill | None:
        """The visit's draft or issued bill (not a cancelled one), without its lines."""
        ...

    def credit_notes_for(self, bill_id: UUID) -> Sequence[Bill]:
        """The bill's credit notes, oldest first, with their lines."""
        ...

    def next_seq(self, kind: BillKind, financial_year: str) -> int:
        """The next number in a series; the caller holds the clinic row lock (B5)."""
        ...

    def list(self, query: BillQuery) -> Sequence[Bill]:
        """Bills (never credit notes), newest first, without their lines."""
        ...

    def dues(self, *, patient_id: UUID | None = None, limit: int = 200) -> Sequence[PatientDues]:
        """Patients with a positive balance on issued bills, the largest first (R39)."""
        ...

    def dues_for(self, patient_ids: Sequence[UUID]) -> dict[UUID, int]:
        """What each of these patients owes; patients who owe nothing are left out (R40)."""
        ...


class PaymentRepository(Protocol):
    """``payments`` of one clinic (M6d-P3)."""

    def add(self, payment: Payment) -> None: ...
    def update(self, payment: Payment) -> None:
        """Only a void changes a payment."""
        ...

    def get(self, payment_id: UUID, *, for_update: bool = False) -> Payment | None: ...
    def list_for_bill(self, bill_id: UUID) -> Sequence[Payment]:
        """Oldest first, voided ones included."""
        ...

    def list_on(self, day: date) -> Sequence[Payment]:
        """Every payment and refund of one clinic-local day, voided ones included (P5)."""
        ...
