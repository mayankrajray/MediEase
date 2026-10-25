"""Clinic — the tenant. Every tenant-owned row belongs to exactly one clinic (ADR-0003).

Lifecycle (spec §3): ``ONBOARDING → ACTIVE ↔ SUSPENDED``. Invariant **I1**: an
``ACTIVE`` clinic has at least one active owner, so activation needs the
clinic's active-owner count from the caller (the domain does no I/O).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mediease_api.domain.booking.request import DEFAULT_HOLD_MINUTES, HOLD_MINUTES_RANGE
from mediease_api.domain.clinics.verification import VerificationSource
from mediease_api.domain.patients.code import derive_code_prefix, format_code, validate_code_prefix
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import DomainError, InvalidTransition, InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import optional_text, required_text
from mediease_api.domain.shared.time import require_utc

DEFAULT_TIMEZONE = "Asia/Kolkata"

# Lower-case words joined by single hyphens; the public page is /c/<slug> (M6b-P4).
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SLUG_LENGTH = range(3, 64)
# Indian PIN code: six digits, never starting with 0.
_PINCODE = re.compile(r"[1-9]\d{5}")


class ClinicStatus(StrEnum):
    ONBOARDING = "ONBOARDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class PaperSize(StrEnum):
    """The clinic's prescription stationery (M4-P4 decision 3A); A5 unless the clinic chooses A4."""

    A5 = "A5"
    A4 = "A4"


REMINDER_HOURS_MAX = 6


class ClinicOwnerRequired(DomainError):
    """I1: a clinic cannot be active without an active owner."""

    code = "CLN_OWNER_REQUIRED"

    def __init__(self) -> None:
        super().__init__("A clinic needs an active owner before it can be activated.")


@dataclass(slots=True)
class Clinic:
    """A clinic. Build new ones with ``Clinic.create``; the constructor rehydrates."""

    id: UUID
    name: str
    slug: str
    timezone: str
    status: ClinicStatus
    phone: PhoneNumber | None
    address_line: str | None
    city: str | None
    state: str | None
    pincode: str | None
    specialties: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    # Patient codes (M2, spec patients R4): the prefix is fixed once a patient exists, and the
    # counter only ever moves forward, so a code is never reused.
    patient_code_prefix: str
    next_patient_seq: int
    # M3 (spec appointments R3, R4): how the clinic's sessions are booked. Changing it is a use case
    # (R19), because every current block must support the new mode.
    booking_mode: BookingMode = BookingMode.TOKENS
    # M4-P4 (decision 3A): applied when a prescription version is first rendered, then fixed in
    # its stored PDF, so changing it never alters a printed prescription.
    rx_paper_size: PaperSize = PaperSize.A5
    # M6a-P8 (FR-APT-08, decision 3A): appointment reminders, the evening before and some hours
    # before the visit (0 = off). Applied to bookings made or moved after a change.
    reminder_evening_before: bool = True
    reminder_hours_before: int = 2
    # M6b-P4 (spec booking-requests R12, R27; ADR-0018): how long an online request holds its
    # slot, and whether the request form must ask age and sex (phone is always asked).
    request_hold_minutes: int = DEFAULT_HOLD_MINUTES
    request_requires_age_sex: bool = False
    # M6c-P3 (FR-ONB-04, 06): verified by a MediEase reviewer, never inferred from the status.
    verified_at: datetime | None = None
    verified_by: UUID | None = None
    verification_source: VerificationSource | None = None
    application_id: UUID | None = None
    # M6c-P4 (FR-ONB-09, 10): the owner's directory listing; P5 (FR-DIS-06): search engines may
    # index the public profiles unless the clinic opts out.
    listed: bool = False
    listed_at: datetime | None = None
    search_indexing: bool = True

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    @property
    def has_public_page(self) -> bool:
        """R1, NFR-19, FR-PUB-01: the one rule for ``/c/{slug}`` and its booking requests:
        ``ACTIVE`` and verified by MediEase (M6c-P3). Listing is not needed (FR-DIS-07)."""
        return self.status is ClinicStatus.ACTIVE and self.is_verified

    def verify(
        self,
        *,
        by: UUID,
        source: VerificationSource,
        now: datetime,
        application_id: UUID | None = None,
    ) -> bool:
        """Record MediEase's verification (R43, R45); False if it was already verified."""
        if self.is_verified:
            return False
        now = require_utc(now, "now")
        self.verified_at = now
        self.verified_by = by
        self.verification_source = source
        self.application_id = application_id
        self.updated_at = now
        return True

    def set_listed(self, listed: bool, *, now: datetime) -> bool:
        """The owner's switch (FR-ONB-10); the caller checks the requirements first."""
        if self.listed == listed:
            return False
        now = require_utc(now, "now")
        self.listed = listed
        self.listed_at = now if listed else None
        self.updated_at = now
        return True

    def set_search_indexing(self, allowed: bool, *, now: datetime) -> None:
        self.search_indexing = allowed
        self.updated_at = require_utc(now, "now")

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        name: str,
        slug: str,
        now: datetime,
        timezone: str = DEFAULT_TIMEZONE,
        phone: PhoneNumber | None = None,
        address_line: str | None = None,
        city: str | None = None,
        state: str | None = None,
        pincode: str | None = None,
        specialties: tuple[str, ...] = (),
        patient_code_prefix: str | None = None,
        booking_mode: BookingMode = BookingMode.TOKENS,
        rx_paper_size: PaperSize = PaperSize.A5,
    ) -> Clinic:
        """A new clinic in ``ONBOARDING`` (FR-ORG-01).

        The patient code prefix (spec patients R4) is derived from the name unless given.
        """
        now = require_utc(now, "now")
        clean_name = required_text(name, "name", max_length=200)
        return cls(
            id=id,
            name=clean_name,
            slug=_validate_slug(slug),
            timezone=_validate_timezone(timezone),
            status=ClinicStatus.ONBOARDING,
            phone=phone,
            address_line=optional_text(address_line, "address_line", max_length=300),
            city=optional_text(city, "city", max_length=100),
            state=optional_text(state, "state", max_length=100),
            pincode=_validate_pincode(pincode),
            specialties=_clean_specialties(specialties),
            created_at=now,
            updated_at=now,
            patient_code_prefix=(
                validate_code_prefix(patient_code_prefix)
                if patient_code_prefix is not None
                else derive_code_prefix(clean_name)
            ),
            next_patient_seq=1,
            booking_mode=booking_mode,
            rx_paper_size=rx_paper_size,
        )

    def allocate_patient_code(self, *, now: datetime) -> str:
        """The next patient code for this clinic, advancing the counter (spec patients R4, R9).

        The caller must hold the clinic row locked (``ClinicRepository.get(..., for_update=True)``)
        and persist the clinic in the same transaction, so two registrations cannot take the same
        number and a rolled-back one leaves no gap.
        """
        code = format_code(self.patient_code_prefix, self.next_patient_seq)
        self.updated_at = require_utc(now, "now")
        self.next_patient_seq += 1
        return code

    def activate(self, *, active_owner_count: int, now: datetime) -> None:
        """``ONBOARDING``/``SUSPENDED`` → ``ACTIVE``; requires an active owner (I1)."""
        if self.status is ClinicStatus.ACTIVE:
            raise InvalidTransition("clinic", self.status, "activate")
        if active_owner_count < 1:
            raise ClinicOwnerRequired()
        self._set_status(ClinicStatus.ACTIVE, now)

    def suspend(self, *, now: datetime) -> None:
        """``ACTIVE`` → ``SUSPENDED``."""
        if self.status is not ClinicStatus.ACTIVE:
            raise InvalidTransition("clinic", self.status, "suspend")
        self._set_status(ClinicStatus.SUSPENDED, now)

    def update_details(
        self,
        *,
        now: datetime,
        name: str | None = None,
        timezone: str | None = None,
        phone: PhoneNumber | None = None,
        address_line: str | None = None,
        city: str | None = None,
        state: str | None = None,
        pincode: str | None = None,
        specialties: tuple[str, ...] | None = None,
        rx_paper_size: PaperSize | None = None,
    ) -> None:
        """Change the clinic's own details (FR-ORG-01, M1-P5).

        Only the fields given are touched, so a caller cannot blank a field by
        omitting it. The slug is not editable: it appears in the public page's
        address (/c/<slug>, M6b-P4), so changing it would break shared links; the status has its own
        transitions. Every value is validated before anything changes.
        """
        validated_name = required_text(name, "name", max_length=200) if name is not None else None
        validated: dict[str, object] = {
            "timezone": _validate_timezone(timezone) if timezone is not None else None,
            "address_line": optional_text(address_line, "address_line", max_length=300),
            "city": optional_text(city, "city", max_length=100),
            "state": optional_text(state, "state", max_length=100),
            "pincode": _validate_pincode(pincode),
            "specialties": _clean_specialties(specialties) if specialties is not None else None,
            "rx_paper_size": rx_paper_size,
        }
        self.updated_at = require_utc(now, "now")
        if validated_name is not None:
            self.name = validated_name
        if phone is not None:
            self.phone = phone
        for attribute, value in validated.items():
            if value is not None:
                setattr(self, attribute, value)

    def change_booking_requests(
        self,
        *,
        now: datetime,
        hold_minutes: int | None = None,
        requires_age_sex: bool | None = None,
    ) -> None:
        """Developer decision 25 Oct 2026: the hold (30 minutes to 8 hours) and whether the
        request form must ask age and sex; only the values given change."""
        if hold_minutes is not None and hold_minutes not in HOLD_MINUTES_RANGE:
            raise InvalidValue("request_hold_minutes", "must be 30-480")
        self.updated_at = require_utc(now, "now")
        if hold_minutes is not None:
            self.request_hold_minutes = hold_minutes
        if requires_age_sex is not None:
            self.request_requires_age_sex = requires_age_sex

    def change_reminders(
        self, *, now: datetime, evening_before: bool | None = None, hours_before: int | None = None
    ) -> None:
        """Decision 3A: the clinic's appointment reminders; only the values given change."""
        if hours_before is not None and not 0 <= hours_before <= REMINDER_HOURS_MAX:
            raise InvalidValue("reminder_hours_before", f"must be 0-{REMINDER_HOURS_MAX}")
        self.updated_at = require_utc(now, "now")
        if evening_before is not None:
            self.reminder_evening_before = evening_before
        if hours_before is not None:
            self.reminder_hours_before = hours_before

    def change_booking_mode(self, mode: BookingMode, *, now: datetime) -> bool:
        """Switch slots/tokens; True if it changed. The caller has checked every block (R19)."""
        if mode is self.booking_mode:
            return False
        self.updated_at = require_utc(now, "now")
        self.booking_mode = mode
        return True

    def _set_status(self, status: ClinicStatus, now: datetime) -> None:
        self.updated_at = require_utc(now, "now")  # validated first: a bad value changes nothing
        self.status = status


def _validate_slug(slug: str) -> str:
    if len(slug) not in _SLUG_LENGTH or not _SLUG.fullmatch(slug):
        raise InvalidValue(
            "slug", "must be 3-63 lower-case letters or digits, separated by single hyphens"
        )
    return slug


def _validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise InvalidValue("timezone", "must be an IANA time zone name") from None
    return name


def _validate_pincode(pincode: str | None) -> str | None:
    cleaned = optional_text(pincode, "pincode", max_length=6)
    if cleaned is not None and not _PINCODE.fullmatch(cleaned):
        raise InvalidValue("pincode", "must be a 6-digit PIN code")
    return cleaned


def _clean_specialties(specialties: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = (required_text(s, "specialties", max_length=100) for s in specialties)
    return tuple(dict.fromkeys(cleaned))  # de-duplicated, order kept
