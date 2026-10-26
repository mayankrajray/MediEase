"""The fee schedule (M6d-P1; FR-BIL-01; spec billing R1-R12).

``GetFees`` reads the schedule with each doctor's prices (``BILLING_MANAGE``: every role drafts
bills from it); ``AddService``, ``ChangeService`` and ``SetDoctorPrice`` are the owner's
(``FEES_MANAGE``). Every change is audited with IDs, the kind and amounts in paise.
``consultation_prices`` is the public profile's fee (D8), shared with the public reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.billing.fees import (
    MAX_SERVICES,
    ClinicService,
    ServiceKind,
    TooManyServices,
    check_unique_name,
    consultation_service,
    default_services,
    price_for,
)
from mediease_api.domain.billing.money import check_price
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY = "clinic_service"


@dataclass(frozen=True, slots=True)
class FeeSchedule:
    services: tuple[ClinicService, ...]
    doctors: tuple[Doctor, ...]  # the clinic's active doctors
    # (service ID, doctor ID) -> the doctor's own price
    prices: Mapping[tuple[UUID, UUID], int]

    def price(self, service: ClinicService, doctor_id: UUID | None) -> int | None:
        return price_for(service, doctor_id, self.prices)


def load_schedule(tenant: TenantRepositories) -> FeeSchedule:
    prices = {(p.service_id, p.doctor_id): p.price_paise for p in tenant.fees.list_prices()}
    doctors = tuple(d for d in tenant.doctors.list() if d.is_active)
    return FeeSchedule(tuple(tenant.fees.list_services()), doctors, prices)


def consultation_prices(tenant: TenantRepositories) -> dict[UUID, int | None]:
    """D8, R10: each doctor's price for the clinic's first active consultation service."""
    schedule = load_schedule(tenant)
    service = consultation_service(schedule.services)
    return {
        d.id: (schedule.price(service, d.id) if service is not None else None)
        for d in tenant.doctors.list()
    }


def add_default_services(
    tenant: TenantRepositories, clinic_id: UUID, ids: IdPort, now: datetime
) -> None:
    """R2: a new clinic's *Consultation* and *Follow-up* (clinic creation and the seed)."""
    for service in default_services(clinic_id, (ids.new_id() for _ in range(2)), now):
        tenant.fees.add_service(service)


class _UseCase:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids


class GetFees:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, ctx: RequestContext) -> FeeSchedule:
        with self._uow as uow:
            return load_schedule(uow.tenant(ctx.clinic_id))


@dataclass(frozen=True, slots=True)
class ServiceCommand:
    name: str | None = None
    kind: ServiceKind | None = None
    default_price_paise: int | None = None
    clear_default_price: bool = False
    active: bool | None = None
    position: int | None = None


def _lock(uow: UnitOfWork, clinic_id: UUID) -> None:
    """R3: changes to one clinic's schedule happen one at a time (names, the count)."""
    if uow.clinics.get(clinic_id, for_update=True) is None:  # pragma: no cover - the context's
        raise NotFound("clinic")


class AddService(_UseCase):
    def execute(self, ctx: RequestContext, cmd: ServiceCommand) -> FeeSchedule:
        assert cmd.name is not None and cmd.kind is not None  # the delivery model requires them
        with self._uow as uow:
            now = self._clock.now()
            _lock(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            services = tenant.fees.list_services()
            if len(services) >= MAX_SERVICES:
                raise TooManyServices()
            service = ClinicService.create(
                id=self._ids.new_id(),
                clinic_id=ctx.clinic_id,
                name=cmd.name,
                kind=cmd.kind,
                default_price_paise=cmd.default_price_paise,
                position=cmd.position or len(services) + 1,
                now=now,
            )
            check_unique_name(services, service.name)
            tenant.fees.add_service(service)
            _audit(uow, self._ids, ctx, AuditAction.FEES_SERVICE_ADDED, service, now)
            uow.commit()
            schedule = load_schedule(tenant)
        logger.info("fees.service_added", clinic_id=str(ctx.clinic_id), kind=service.kind.value)
        return schedule


class ChangeService(_UseCase):
    def execute(self, ctx: RequestContext, service_id: UUID, cmd: ServiceCommand) -> FeeSchedule:
        with self._uow as uow:
            now = self._clock.now()
            _lock(uow, ctx.clinic_id)
            tenant = uow.tenant(ctx.clinic_id)
            service = tenant.fees.get_service(service_id, for_update=True)
            if service is None:
                raise NotFound("service")
            service.change(
                now=now,
                name=cmd.name,
                kind=cmd.kind,
                default_price_paise=cmd.default_price_paise,
                clear_default_price=cmd.clear_default_price,
                active=cmd.active,
                position=cmd.position,
            )
            if service.active:
                check_unique_name(tenant.fees.list_services(), service.name, except_id=service.id)
            tenant.fees.update_service(service)
            _audit(uow, self._ids, ctx, AuditAction.FEES_SERVICE_CHANGED, service, now)
            uow.commit()
            schedule = load_schedule(tenant)
        return schedule


class SetDoctorPrice(_UseCase):
    """R4: a doctor's own price for a service; ``None`` removes it and the default applies."""

    def execute(
        self, ctx: RequestContext, service_id: UUID, doctor_id: UUID, price_paise: int | None
    ) -> FeeSchedule:
        if price_paise is not None:
            check_price(price_paise, "price_paise")
        with self._uow as uow:
            now = self._clock.now()
            tenant = uow.tenant(ctx.clinic_id)
            service = tenant.fees.get_service(service_id)
            if service is None:
                raise NotFound("service")
            if tenant.doctors.get(doctor_id) is None:
                raise NotFound("doctor")
            tenant.fees.set_price(
                service.id, doctor_id, price_paise, id=self._ids.new_id(), now=now
            )
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.FEES_DOCTOR_PRICE_SET,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY,
                entity_id=service.id,
                metadata={
                    "doctor_id": str(doctor_id),
                    "price_paise": "default" if price_paise is None else str(price_paise),
                },
            )
            uow.commit()
            schedule = load_schedule(tenant)
        return schedule


def _audit(
    uow: UnitOfWork,
    ids: IdPort,
    ctx: RequestContext,
    action: AuditAction,
    service: ClinicService,
    now: datetime,
) -> None:
    record_event(
        uow,
        event_id=ids.new_id(),
        action=action,
        actor=Actor.staff(ctx),
        now=now,
        clinic_id=ctx.clinic_id,
        entity_type=ENTITY,
        entity_id=service.id,
        metadata={
            "kind": service.kind.value,
            "default_price_paise": (
                "none" if service.default_price_paise is None else str(service.default_price_paise)
            ),
            "active": str(service.active).lower(),
        },
    )
