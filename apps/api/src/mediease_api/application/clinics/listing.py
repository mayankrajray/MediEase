"""The owner's directory listing and doctor visibility (M6c-P4; FR-ONB-09, 10; spec R50-R55).

``GetListing`` reports the listing, the problems in the way and each doctor's state;
``SetListing`` turns the listing on (only with no problem, R52) or off (always);
``SetDoctorVisibility`` shows or hides a doctor (showing needs active and verified, R53).
Every change is audited. ``load_listing`` is shared with the public and search reads (P5-P6).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.billing.fees import consultation_prices
from mediease_api.application.context import Actor, RequestContext
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.listing import (
    DoctorListing,
    DoctorNotShowable,
    ListingBlocked,
    ListingProblem,
    is_discoverable,
    listing_problems,
)
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Listing:
    clinic: Clinic
    doctors: tuple[DoctorListing, ...]
    # M6d-P1 (D8): each doctor's consultation price on the fee schedule.
    fees: Mapping[UUID, int | None] = field(default_factory=dict)

    @property
    def problems(self) -> tuple[ListingProblem, ...]:
        return listing_problems(self.clinic, self.doctors)

    @property
    def discoverable(self) -> bool:
        return is_discoverable(self.clinic, self.doctors)


def load_listing(uow: UnitOfWork, clinic: Clinic, now: datetime) -> Listing:
    """The clinic's doctors with whether each has a weekly schedule in force today."""
    tenant = uow.tenant(clinic.id)
    today = now.astimezone(ZoneInfo(clinic.timezone)).date()
    doctors = tuple(
        DoctorListing(d, bool(tenant.schedules.list_for_doctor(d.id, valid_since=today)))
        for d in tenant.doctors.list()
    )
    return Listing(clinic, doctors, consultation_prices(tenant))


def _clinic(uow: UnitOfWork, clinic_id: UUID, *, lock: bool = False) -> Clinic:
    clinic = uow.clinics.get(clinic_id, for_update=lock)
    if clinic is None:  # pragma: no cover - the context names an existing clinic
        raise NotFound("clinic")
    return clinic


class GetListing:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext) -> Listing:
        with self._uow as uow:
            return load_listing(uow, _clinic(uow, ctx.clinic_id), self._clock.now())


class SetListing:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, ctx: RequestContext, listed: bool | None, search_indexing: bool | None = None
    ) -> Listing:
        with self._uow as uow:
            now = self._clock.now()
            clinic = _clinic(uow, ctx.clinic_id, lock=True)
            listing = load_listing(uow, clinic, now)
            if search_indexing is not None and search_indexing != clinic.search_indexing:
                # M6c-P5 (R62): the owner's opt-out of search engines.
                clinic.set_search_indexing(search_indexing, now=now)
                uow.clinics.update(clinic)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.CLINIC_LISTING_CHANGED,
                    actor=Actor.staff(ctx),
                    now=now,
                    clinic_id=clinic.id,
                    metadata={"search_indexing": str(search_indexing).lower()},
                )
            if listed is None:
                uow.commit()
                return load_listing(uow, clinic, now)
            if listed and listing.problems:
                raise ListingBlocked(listing.problems)
            if clinic.set_listed(listed, now=now):
                uow.clinics.update(clinic)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.CLINIC_LISTING_CHANGED,
                    actor=Actor.staff(ctx),
                    now=now,
                    clinic_id=clinic.id,
                    metadata={"listed": str(listed).lower()},
                )
                logger.info("clinic.listing_changed", clinic_id=str(clinic.id), listed=listed)
            uow.commit()
            return load_listing(uow, clinic, now)


class SetDoctorVisibility:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, doctor_id: UUID, visible: bool) -> Listing:
        with self._uow as uow:
            now = self._clock.now()
            clinic = _clinic(uow, ctx.clinic_id)
            doctors = uow.tenant(clinic.id).doctors
            doctor = doctors.get(doctor_id)
            if doctor is None:
                raise NotFound("doctor")
            if visible and not (doctor.is_active and doctor.is_verified):
                raise DoctorNotShowable()
            if doctor.visible != visible:
                doctor.set_visible(visible, now=now)
                doctors.update(doctor)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.DOCTOR_VISIBILITY_CHANGED,
                    actor=Actor.staff(ctx),
                    now=now,
                    clinic_id=clinic.id,
                    entity_type="doctor",
                    entity_id=doctor.id,
                    metadata={"visible": str(visible).lower()},
                )
            uow.commit()
            return load_listing(uow, clinic, now)


class SetDoctorProfile:
    """M6c-P5 (R61): the languages a doctor speaks (from the published list); M6d-P1 (D8):
    whether their consultation price is shown on the public profile. Owners (``CLINIC_MANAGE``)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self,
        ctx: RequestContext,
        doctor_id: UUID,
        *,
        languages: tuple[str, ...] | None,
        show_fee: bool | None,
    ) -> Listing:
        with self._uow as uow:
            now = self._clock.now()
            clinic = _clinic(uow, ctx.clinic_id)
            doctors = uow.tenant(clinic.id).doctors
            doctor = doctors.get(doctor_id)
            if doctor is None:
                raise NotFound("doctor")
            doctor.set_profile(languages=languages, show_fee=show_fee, now=now)
            doctors.update(doctor)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.DOCTOR_VISIBILITY_CHANGED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=clinic.id,
                entity_type="doctor",
                entity_id=doctor.id,
                metadata={
                    "profile": "updated",
                    "languages": str(len(doctor.languages)),
                    "show_fee": str(doctor.show_fee).lower(),
                },
            )
            uow.commit()
            return load_listing(uow, clinic, now)
