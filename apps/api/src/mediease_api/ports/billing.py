"""Billing repositories (M6d), each tenant-scoped (ADR-0003)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.billing.bill import Bill, BillKind, BillStatus
from mediease_api.domain.billing.fees import ClinicService, DoctorPrice


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
