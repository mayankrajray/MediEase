"""The public clinic page and its availability (M6b-P4; FR-PUB-01, FR-DIS-05, NFR-17, NFR-19).

No session. A clinic that is not ``has_public_page`` is exactly an unknown slug: the same
``NotFound`` for the page, its availability and a request. Only published fields leave this
module (the delivery body is an allow-list, tested): the clinic's name and address, phone, hours
from its doctors' weekly blocks, and each active doctor's name, qualification and specialty.
Availability is computed from the plan and the existing rows **without writing**: a session is
created only when a request is made for it (R8).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from urllib.parse import quote
from uuid import UUID

import structlog

from mediease_api.application.booking.limits import limit_reads
from mediease_api.application.clinics.listing import load_listing
from mediease_api.application.context import RequestInfo
from mediease_api.domain.booking.request import HORIZON_DAYS, MIN_LEAD
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import SessionStatus, horizon, plan_day
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PublicHours:
    weekday: int  # 0 = Monday
    start: time
    end: time


@dataclass(frozen=True, slots=True)
class PublicDoctor:
    id: UUID
    display_name: str
    qualification: str
    specialty: str | None
    hours: tuple[PublicHours, ...]
    # M6c-P5 (FR-DIS-03): the published profile.
    languages: tuple[str, ...] = ()
    fee_paise: int | None = None


@dataclass(frozen=True, slots=True)
class PublicClinic:
    clinic: Clinic
    map_url: str
    doctors: tuple[PublicDoctor, ...]
    # M6c-P5 (FR-DIS-06, R62): search engines may index it: discoverable and not opted out.
    indexable: bool = False


@dataclass(frozen=True, slots=True)
class SitemapEntry:
    slug: str
    updated_at: datetime
    doctor_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SlotOffer:
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class SessionOffer:
    starts_at: datetime
    ends_at: datetime
    mode: BookingMode
    places_left: int
    slots: tuple[SlotOffer, ...]  # the free slots (slot mode); empty in token mode


@dataclass(frozen=True, slots=True)
class DayOffer:
    on_date: date
    sessions: tuple[SessionOffer, ...]


def map_link(clinic: Clinic) -> str:
    """A maps search for the clinic's own address (no coordinates are stored)."""
    parts = [clinic.name, clinic.address_line, clinic.city, clinic.state, clinic.pincode]
    return "https://www.google.com/maps/search/?api=1&query=" + quote(
        ", ".join(p for p in parts if p), safe=""
    )


def find_public_clinic(uow: UnitOfWork, slug: str) -> Clinic:
    """R1, NFR-19: unknown and not-public are one answer. The slug is logged only as a digest."""
    clinic = uow.clinics.get_by_slug(slug)
    if clinic is None or not clinic.has_public_page:
        logger.info("public.page_not_found", slug_digest=sha256(slug.encode()).hexdigest()[:12])
        raise NotFound("clinic")
    return clinic


class GetPublicClinic:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, slug: str, info: RequestInfo) -> PublicClinic:
        limit_reads(self._uow, self._clock, info)
        with self._uow as uow:
            clinic = find_public_clinic(uow, slug)
            tenant = uow.tenant(clinic.id)
            today = local_date(self._clock.now(), clinic.timezone)
            doctors = []
            for doctor in tenant.doctors.list():
                if not doctor.is_public:  # M6c-P5 (R59): active, verified and shown
                    continue
                blocks = tenant.schedules.list_for_doctor(doctor.id, valid_since=today)
                hours = sorted(
                    {PublicHours(b.weekday, b.shape.start_time, b.shape.end_time) for b in blocks},
                    key=lambda h: (h.weekday, h.start),
                )
                doctors.append(
                    PublicDoctor(
                        doctor.id,
                        doctor.display_name,
                        doctor.qualification,
                        doctor.specialty,
                        tuple(hours),
                        doctor.languages,
                        doctor.fee_paise,
                    )
                )
            listing = load_listing(uow, clinic, self._clock.now())
            indexable = listing.discoverable and clinic.search_indexing
        return PublicClinic(clinic, map_link(clinic), tuple(doctors), indexable)


def build_offers(
    tenant: TenantRepositories, clinic: Clinic, doctor: Doctor, first: date, now: datetime
) -> list[DayOffer]:
    """R6, R7: the next 14 days for one doctor, from the plan minus booked slots and live holds."""
    days = [first + timedelta(days=n) for n in range(HORIZON_DAYS)]
    blocks = tenant.schedules.list_for_doctor(doctor.id, valid_since=first)
    exceptions = tenant.schedule_exceptions.list_for_doctor(doctor.id, first=first, last=days[-1])
    rows = {
        s.key: s for s in tenant.sessions.list_for_doctor(doctor.id, first=first, last=days[-1])
    }
    ids = [s.id for s in rows.values()]
    taken: dict[UUID, set[datetime]] = defaultdict(set)
    for appointment in tenant.appointments.list_active_for_sessions(ids):
        if appointment.slot_start is not None:
            taken[appointment.session_id].add(appointment.slot_start)
    held_slots: dict[UUID, set[datetime]] = defaultdict(set)
    held_count: dict[UUID, int] = defaultdict(int)
    for hold in tenant.booking_requests.live_holds(ids, now):
        held_count[hold.session_id] += 1
        if hold.slot_start is not None:
            held_slots[hold.session_id].add(hold.slot_start)

    earliest = now + MIN_LEAD
    offers: list[DayOffer] = []
    for day in days:
        sessions: list[SessionOffer] = []
        for plan in plan_day(
            doctor_id=doctor.id,
            on_date=day,
            timezone=clinic.timezone,
            mode=clinic.booking_mode,
            blocks=blocks,
            exceptions=exceptions,
        ):
            row = rows.get(plan.key)
            if row is not None and row.status is SessionStatus.CLOSED:
                continue  # a schedule change closed it; not offered
            live = row if row is not None and row.status is SessionStatus.OPEN else None
            sid = live.id if live is not None else None
            booked = live.booked_count if live is not None else 0
            capacity = live.capacity if live is not None else plan.capacity
            holds = held_count[sid] if sid is not None else 0
            if plan.mode is BookingMode.SLOTS:
                grid = plan.slots()
                if not grid or grid[-1][0] < earliest:
                    continue
                busy = (taken[sid] | held_slots[sid]) if sid is not None else set()
                free = tuple(SlotOffer(s, e) for s, e in grid if s >= earliest and s not in busy)
                # Free slots already exclude booked and held ones (each takes one place).
                if free:  # nothing left to ask for is not offered
                    sessions.append(
                        SessionOffer(plan.starts_at, plan.ends_at, plan.mode, len(free), free)
                    )
            else:
                if plan.starts_at < earliest:
                    continue
                left = max(0, capacity - booked - holds)
                if left > 0:
                    sessions.append(SessionOffer(plan.starts_at, plan.ends_at, plan.mode, left, ()))
        if sessions:  # a day with nothing to offer is left out (spec R7)
            offers.append(DayOffer(day, tuple(sessions)))
    return offers


class GetAvailability:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self, slug: str, doctor_id: UUID, first: date | None, info: RequestInfo
    ) -> Sequence[DayOffer]:
        limit_reads(self._uow, self._clock, info)
        now = self._clock.now()
        with self._uow as uow:
            clinic = find_public_clinic(uow, slug)
            tenant = uow.tenant(clinic.id)
            doctor = tenant.doctors.get(doctor_id)
            if doctor is None or not doctor.is_public:
                raise NotFound("doctor")
            today = local_date(now, clinic.timezone)
            start = first or today
            if start < today or start > horizon(today) - timedelta(days=HORIZON_DAYS):
                raise InvalidValue("from", "must be today or a day within the next 180 days")
            return build_offers(tenant, clinic, doctor, start, now)


# M6c-P5 (FR-DIS-06, R62, R63): at most this many clinics in the sitemap (pilot scale; one file).
SITEMAP_LIMIT = 5_000


class GetSitemap:
    """The indexable profiles: discoverable clinics that have not opted out, with their shown
    doctors. Unlisted, unverified, suspended and opted-out clinics are simply absent."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self) -> list[SitemapEntry]:
        now = self._clock.now()
        entries: list[SitemapEntry] = []
        with self._uow as uow:
            for clinic in uow.clinics.list_listed(limit=SITEMAP_LIMIT):
                if not clinic.search_indexing:
                    continue
                listing = load_listing(uow, clinic, now)
                if not listing.discoverable:
                    continue
                shown = tuple(d.doctor.id for d in listing.doctors if d.is_shown)
                entries.append(SitemapEntry(clinic.slug, clinic.updated_at, shown))
        return entries
