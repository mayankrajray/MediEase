"""The clinic's fee schedule (M6d-P1; FR-BIL-01; spec billing R1-R12).

A clinic has **services** (consultation, follow-up, procedure, other), each with an optional
default price; a doctor may have their own price for a service. A doctor's price for a service is
their own if set, else the service's default, else none (R4). Prices change from now on only:
bills copy what they charge (decision B3), so nothing here is ever read back from a bill.

The public profile fee (M6c-P5, D8) is the doctor's price for the clinic's first active
consultation service, shown only when the owner turns it on for that doctor (``Doctor.show_fee``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.billing.money import check_price
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.text import required_text
from mediease_api.domain.shared.time import require_utc

NAME_MAX = 80
# R3: a clinic's schedule stays short enough to read on one screen.
MAX_SERVICES = 100


class ServiceKind(StrEnum):
    CONSULTATION = "CONSULTATION"
    FOLLOW_UP = "FOLLOW_UP"
    PROCEDURE = "PROCEDURE"
    OTHER = "OTHER"


class ServiceNameTaken(DomainError):
    """R3: two active services cannot share a name (ignoring case)."""

    code = "BIL_SERVICE_NAME_TAKEN"

    def __init__(self) -> None:
        super().__init__("Another active service already has this name.", field="name")


class TooManyServices(DomainError):
    code = "BIL_TOO_MANY_SERVICES"

    def __init__(self) -> None:
        super().__init__(f"A clinic can have at most {MAX_SERVICES} services.")


@dataclass(slots=True)
class ClinicService:
    """One line of the fee schedule. Build new ones with ``create``."""

    id: UUID
    clinic_id: UUID
    name: str
    kind: ServiceKind
    default_price_paise: int | None
    active: bool
    position: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        name: str,
        kind: ServiceKind,
        default_price_paise: int | None,
        position: int,
        now: datetime,
    ) -> ClinicService:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            name=_name(name),
            kind=kind,
            default_price_paise=_price(default_price_paise, "default_price_paise"),
            active=True,
            position=position,
            created_at=now,
            updated_at=now,
        )

    def change(
        self,
        *,
        now: datetime,
        name: str | None = None,
        kind: ServiceKind | None = None,
        default_price_paise: int | None = None,
        clear_default_price: bool = False,
        active: bool | None = None,
        position: int | None = None,
    ) -> None:
        """R5: only the values given change; a retired service may be brought back."""
        cleaned = _name(name) if name is not None else None
        price = _price(default_price_paise, "default_price_paise")
        if position is not None and not 1 <= position <= MAX_SERVICES:
            raise InvalidValue("position", f"must be 1-{MAX_SERVICES}")
        self.updated_at = require_utc(now, "now")
        if cleaned is not None:
            self.name = cleaned
        if kind is not None:
            self.kind = kind
        if clear_default_price:
            self.default_price_paise = None
        elif price is not None:
            self.default_price_paise = price
        if active is not None:
            self.active = active
        if position is not None:
            self.position = position


@dataclass(frozen=True, slots=True)
class DoctorPrice:
    """A doctor's own price for one service (R4)."""

    service_id: UUID
    doctor_id: UUID
    price_paise: int


def default_services(clinic_id: UUID, new_id: Iterable[UUID], now: datetime) -> list[ClinicService]:
    """R2: every clinic starts with *Consultation* and *Follow-up*, without prices."""
    ids = iter(new_id)
    return [
        ClinicService.create(
            id=next(ids),
            clinic_id=clinic_id,
            name=name,
            kind=kind,
            default_price_paise=None,
            position=position,
            now=now,
        )
        for position, (name, kind) in enumerate(
            (("Consultation", ServiceKind.CONSULTATION), ("Follow-up", ServiceKind.FOLLOW_UP)),
            start=1,
        )
    ]


def price_for(
    service: ClinicService, doctor_id: UUID | None, prices: Mapping[tuple[UUID, UUID], int]
) -> int | None:
    """R4: the doctor's own price, else the default, else none."""
    if doctor_id is not None:
        own = prices.get((service.id, doctor_id))
        if own is not None:
            return own
    return service.default_price_paise


def consultation_service(services: Sequence[ClinicService]) -> ClinicService | None:
    """R10, D8: the clinic's first active consultation, in the schedule's order."""
    for service in sorted(services, key=lambda s: (s.position, s.name.lower())):
        if service.active and service.kind is ServiceKind.CONSULTATION:
            return service
    return None


def check_unique_name(
    services: Sequence[ClinicService], name: str, *, except_id: UUID | None = None
) -> None:
    wanted = name.strip().lower()
    for service in services:
        if service.active and service.id != except_id and service.name.lower() == wanted:
            raise ServiceNameTaken()


def _name(name: str) -> str:
    return required_text(name, "name", max_length=NAME_MAX)


def _price(paise: int | None, field: str) -> int | None:
    return None if paise is None else check_price(paise, field)
