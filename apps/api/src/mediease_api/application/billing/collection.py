"""The daily collection and its CSV (M6d-P5; FR-BIL-06; spec billing R55-R62).

``COLLECTION_VIEW`` (owners and the front desk). A clinic-local day, today unless asked; never
a future day. The export is the same list as the screen and is itself audited
(``collection.exported``: the day and the row count). Reading is not audited.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.billing.bill import Bill
from mediease_api.domain.billing.collection import Collection, summarise
from mediease_api.domain.billing.payment import Payment
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CollectionDay:
    day: date
    timezone: str
    clinic_slug: str
    summary: Collection
    payments: tuple[Payment, ...]
    bills: Mapping[UUID, Bill]
    patients: Mapping[UUID, Patient]
    doctors: Mapping[UUID, Doctor]
    people: Mapping[UUID, str]


class GetCollection:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext, day: date | None) -> CollectionDay:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            today = local_date(self._clock.now(), clinic.timezone)
            day = day or today
            if day > today:
                raise InvalidValue("date", "must not be in the future")
            tenant = uow.tenant(ctx.clinic_id)
            payments = tuple(tenant.payments.list_on(day))
            bills = {b.id: b for b in tenant.bills.get_many({p.bill_id for p in payments})}
            patients = {p.id: p for p in tenant.patients.get_many({p.patient_id for p in payments})}
            doctors = {d.id: d for d in tenant.doctors.list()}
            people: dict[UUID, str] = {}
            for user_id in {p.received_by for p in payments}:
                user = uow.users.get(user_id)
                if user is not None:
                    people[user_id] = user.full_name
        return CollectionDay(
            day,
            clinic.timezone,
            clinic.slug,
            summarise(payments),
            payments,
            bills,
            patients,
            doctors,
            people,
        )


class ExportCollection:
    """R60: the day's list as CSV; the export is audited."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._get = GetCollection(uow=uow, clock=clock)
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, day: date | None) -> CollectionDay:
        result = self._get.execute(ctx, day)
        with self._uow as uow:
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.COLLECTION_EXPORTED,
                actor=Actor.staff(ctx),
                now=self._clock.now(),
                clinic_id=ctx.clinic_id,
                metadata={"date": result.day.isoformat(), "rows": str(len(result.payments))},
            )
            uow.commit()
        logger.info("collection.exported", clinic_id=str(ctx.clinic_id), rows=len(result.payments))
        return result
