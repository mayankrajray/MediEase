"""Clinic and doctor search (M6c-P6; FR-DIS-01, 02, 04, 05; spec discovery R1-R10; ADR-0021).

No session. The directory reader proposes candidates from every clinic (IDs, a relevance score
and a place rank); each candidate then passes the **one discoverability rule** (``load_listing``,
R55 of clinic-onboarding) and only public doctors are shown, so search can never show what the
public page would not. Availability ("a free time in the next 7 days") comes from the same offer
builder as the public page, without writing.

Order (R5): relevance (in steps of 0.1), then place (same PIN, same city, same PIN district,
elsewhere), then the earliest free day, then the name.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.booking.limits import limit_reads
from mediease_api.application.booking.public import build_offers
from mediease_api.application.clinics.listing import Listing, load_listing
from mediease_api.application.context import RequestInfo
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.verification import LANGUAGES
from mediease_api.domain.onboarding.lists import SPECIALTIES
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.directory import DirectoryFilter
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# R2: how many candidates are checked against the rule, and how many results are returned.
CANDIDATES = 40
MAX_RESULTS = 20
# R4: "available" means a free time within this many days, today included.
AVAILABLE_DAYS = 7
Q_MAX = 100
_PIN = re.compile(r"[1-9]\d{5}")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class SearchQuery:
    q: str = ""
    city: str | None = None
    pincode: str | None = None
    specialty: str | None = None
    language: str | None = None
    available: bool = False

    def normalised(self) -> DirectoryFilter:
        """R1: validated and normalised, the value never echoed in an error."""
        q = _SPACES.sub(" ", self.q).strip().lower()
        if len(q) > Q_MAX:
            raise InvalidValue("q", f"must be at most {Q_MAX} characters")
        pincode = (self.pincode or "").strip() or None
        if pincode is not None and not _PIN.fullmatch(pincode):
            raise InvalidValue("pincode", "must be a 6-digit PIN code")
        city = _SPACES.sub(" ", self.city or "").strip().lower() or None
        if city is not None and len(city) > 100:
            raise InvalidValue("city", "must be at most 100 characters")
        specialty = (self.specialty or "").strip() or None
        if specialty is not None and len(specialty) > 100:
            raise InvalidValue("specialty", "must be at most 100 characters")
        language = (self.language or "").strip() or None
        if language is not None and language not in LANGUAGES:
            raise InvalidValue("language", "is not on the list")
        return DirectoryFilter(q, city, pincode, specialty, language)


@dataclass(frozen=True, slots=True)
class ClinicHit:
    clinic: Clinic
    doctors: tuple[Doctor, ...]
    next_available: date | None


@dataclass(frozen=True, slots=True)
class DoctorHit:
    clinic: Clinic
    doctor: Doctor
    next_available: date | None


@dataclass(frozen=True, slots=True)
class SearchOptions:
    specialties: tuple[str, ...] = SPECIALTIES
    languages: tuple[str, ...] = LANGUAGES


def _next_free(
    uow: UnitOfWork, clinic: Clinic, doctor: Doctor, today: date, now: datetime
) -> date | None:
    """R4: the first day within 7 days with a free time for this doctor (no writes)."""
    tenant = uow.tenant(clinic.id)
    last = today + timedelta(days=AVAILABLE_DAYS - 1)
    for day in build_offers(tenant, clinic, doctor, today, now):
        if day.on_date <= last:
            return day.on_date
        break
    return None


def _earliest(days: Sequence[date | None]) -> date | None:
    known = [d for d in days if d is not None]
    return min(known) if known else None


def _sort_key(
    score: float, place: int, free: date | None, name: str
) -> tuple[float, int, int, date, str]:
    return (-round(score, 1), place, 0 if free is not None else 1, free or date.max, name.lower())


class SearchClinics:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, query: SearchQuery, info: RequestInfo) -> list[ClinicHit]:
        f = query.normalised()
        limit_reads(self._uow, self._clock, info)
        now = self._clock.now()
        ranked: list[tuple[tuple[float, int, int, date, str], ClinicHit]] = []
        with self._uow as uow:
            for candidate in uow.directory.clinics(f, limit=CANDIDATES):
                clinic = uow.clinics.get(candidate.clinic_id)
                if clinic is None:
                    continue
                listing: Listing = load_listing(uow, clinic, now)
                if not listing.discoverable:
                    continue
                today = local_date(now, clinic.timezone)
                shown = tuple(d for d in listing.doctors if d.is_shown)
                free = _earliest(
                    [_next_free(uow, clinic, d.doctor, today, now) for d in shown if d.has_schedule]
                )
                if query.available and free is None:
                    continue
                hit = ClinicHit(clinic, tuple(d.doctor for d in shown), free)
                ranked.append((_sort_key(candidate.score, candidate.place, free, clinic.name), hit))
        ranked.sort(key=lambda pair: pair[0])
        results = [hit for _, hit in ranked[:MAX_RESULTS]]
        logger.info(
            "search.clinics", results=len(results), q=bool(f.q), near=bool(f.city or f.pincode)
        )
        return results


class SearchDoctors:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, query: SearchQuery, info: RequestInfo) -> list[DoctorHit]:
        f = query.normalised()
        limit_reads(self._uow, self._clock, info)
        now = self._clock.now()
        ranked: list[tuple[tuple[float, int, int, date, str], DoctorHit]] = []
        listings: dict[UUID, Listing | None] = {}
        with self._uow as uow:
            for candidate in uow.directory.doctors(f, limit=CANDIDATES):
                if candidate.clinic_id not in listings:
                    clinic = uow.clinics.get(candidate.clinic_id)
                    listing = load_listing(uow, clinic, now) if clinic is not None else None
                    listings[candidate.clinic_id] = (
                        listing if listing is not None and listing.discoverable else None
                    )
                listing = listings[candidate.clinic_id]
                if listing is None:
                    continue
                entry = next(
                    (d for d in listing.doctors if d.doctor.id == candidate.doctor_id), None
                )
                if entry is None or not entry.is_shown:
                    continue
                clinic = listing.clinic
                today = local_date(now, clinic.timezone)
                free = (
                    _next_free(uow, clinic, entry.doctor, today, now)
                    if entry.has_schedule
                    else None
                )
                if query.available and free is None:
                    continue
                hit = DoctorHit(clinic, entry.doctor, free)
                key = _sort_key(candidate.score, candidate.place, free, entry.doctor.display_name)
                ranked.append((key, hit))
        ranked.sort(key=lambda pair: pair[0])
        results = [hit for _, hit in ranked[:MAX_RESULTS]]
        logger.info(
            "search.doctors", results=len(results), q=bool(f.q), near=bool(f.city or f.pincode)
        )
        return results
