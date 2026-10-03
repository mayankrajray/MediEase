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

from mediease_api.domain.patients.code import derive_code_prefix, format_code, validate_code_prefix
from mediease_api.domain.shared.errors import DomainError, InvalidTransition, InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import optional_text, required_text
from mediease_api.domain.shared.time import require_utc

DEFAULT_TIMEZONE = "Asia/Kolkata"

# Lower-case words joined by single hyphens; used in public URLs from M7.
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SLUG_LENGTH = range(3, 64)
# Indian PIN code: six digits, never starting with 0.
_PINCODE = re.compile(r"[1-9]\d{5}")


class ClinicStatus(StrEnum):
    ONBOARDING = "ONBOARDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


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
    ) -> None:
        """Change the clinic's own details (FR-ORG-01, M1-P5).

        Only the fields given are touched, so a caller cannot blank a field by
        omitting it. The slug is not editable: it appears in public links from
        M7, so changing it would break them; the status has its own
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
        }
        self.updated_at = require_utc(now, "now")
        if validated_name is not None:
            self.name = validated_name
        if phone is not None:
            self.phone = phone
        for attribute, value in validated.items():
            if value is not None:
                setattr(self, attribute, value)

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
