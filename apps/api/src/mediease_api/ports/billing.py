"""Billing repositories (M6d), each tenant-scoped (ADR-0003)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

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
