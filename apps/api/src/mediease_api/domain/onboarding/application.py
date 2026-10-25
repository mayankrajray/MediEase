"""A clinic's application to join MediEase (M6c; FR-ONB-01, 02, 07; ADR-0020).

Platform data: no clinic exists until a reviewer approves (P3), so an application has no
``clinic_id`` and is never tenant data. The applicant has no account; the owner's email is proved
by a single-use link whose digest the application holds (``confirm_digest``) until it is used.

Lifecycle (spec clinic-onboarding §3): ``PENDING`` (submitted; in the reviewer queue once the
email is confirmed) -> ``UNDER_REVIEW`` -> ``APPROVED | REJECTED``. P1 writes only ``PENDING``;
the review transitions are here so P2 uses one tested state machine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.onboarding.certificate import Certificate
from mediease_api.domain.onboarding.lists import is_council, is_specialty
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import (
    DomainError,
    InvalidTransition,
    InvalidValue,
    NotFound,
)
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.text import required_text
from mediease_api.domain.shared.time import require_utc

MAX_DOCTORS = 10
MAX_SPECIALTIES = 10
# R11, R14: the confirmation link works 48 hours; an unconfirmed application is deleted at 72.
CONFIRM_TTL = timedelta(hours=48)
UNCONFIRMED_RETENTION = timedelta(hours=72)

_PINCODE = re.compile(r"[1-9]\d{5}")
_INDIAN_MOBILE = re.compile(r"\+91[6-9]\d{9}")
_SPACES = re.compile(r"\s+")


class ApplicationKind(StrEnum):
    CLINIC = "CLINIC"
    SOLO_DOCTOR = "SOLO_DOCTOR"


class ApplicationStatus(StrEnum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RejectReason(StrEnum):
    """R33: why an application was not approved; the applicant reads ``REJECT_WORDS``."""

    REGISTRATION_NOT_FOUND = "REGISTRATION_NOT_FOUND"
    CERTIFICATE_UNCLEAR = "CERTIFICATE_UNCLEAR"
    DETAILS_DO_NOT_MATCH = "DETAILS_DO_NOT_MATCH"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    DUPLICATE = "DUPLICATE"
    OTHER = "OTHER"


REJECT_WORDS: dict[RejectReason, str] = {
    RejectReason.REGISTRATION_NOT_FOUND: (
        "We could not find a doctor's registration in the medical council's register."
    ),
    RejectReason.CERTIFICATE_UNCLEAR: "A registration certificate could not be read or checked.",
    RejectReason.DETAILS_DO_NOT_MATCH: (
        "The details on a certificate do not match the details in the application."
    ),
    RejectReason.NOT_ELIGIBLE: "MediEase cannot list this practice at present.",
    RejectReason.DUPLICATE: "This practice has already applied or is already on MediEase.",
    RejectReason.OTHER: "We could not approve the application.",
}
MAX_MESSAGE = 500
# R35: rejected applications are deleted with their certificates this long after the decision.
REJECTED_RETENTION = timedelta(days=180)


class CheckResult(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"


class AlreadyTaken(DomainError):
    """R27: another reviewer took this application first."""

    code = "ONB_ALREADY_TAKEN"

    def __init__(self) -> None:
        super().__init__("Another reviewer has already taken this application.")


class NotUnderReview(DomainError):
    """R29, R33: checks and decisions only while the application is under review."""

    code = "ONB_NOT_UNDER_REVIEW"

    def __init__(self) -> None:
        super().__init__("This application is not under review.")


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """R29, R30: a reviewer's check of one doctor's registration; a new check replaces it."""

    doctor_id: UUID
    checked_by: UUID
    checked_at: datetime
    register_checked: bool
    certificate_matches: bool
    result: CheckResult
    note: str | None = None

    @classmethod
    def record(
        cls,
        *,
        doctor_id: UUID,
        checked_by: UUID,
        now: datetime,
        register_checked: bool,
        certificate_matches: bool,
        result: CheckResult,
        note: str | None,
    ) -> DoctorCheck:
        if result is CheckResult.VERIFIED and not (register_checked and certificate_matches):
            raise InvalidValue("result", "VERIFIED needs the register and the certificate checked")
        clean = note.strip() if note else None
        if clean is not None and len(clean) > MAX_MESSAGE:
            raise InvalidValue("note", f"must be at most {MAX_MESSAGE} characters")
        return cls(
            doctor_id=doctor_id,
            checked_by=checked_by,
            checked_at=require_utc(now, "now"),
            register_checked=register_checked,
            certificate_matches=certificate_matches,
            result=result,
            note=clean or None,
        )


class ApplicationRateLimited(DomainError):
    """R16, NFR-19: too many applications from this address, phone or email today."""

    code = "ONB_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many applications. Please try again later.")
        self.retry_after_seconds = retry_after_seconds


class ConfirmInvalid(DomainError):
    """R12: one answer for an unknown, used or expired confirmation link."""

    code = "ONB_CONFIRM_INVALID"

    def __init__(self) -> None:
        super().__init__("This link is not valid any more.")


class UploadFailed(DomainError):
    """R10: a certificate could not be stored; nothing was kept."""

    code = "ONB_UPLOAD_FAILED"

    def __init__(self) -> None:
        super().__init__("Your files could not be saved. Please try again in a few minutes.")


def normalise_registration(number: str, field: str) -> str:
    """R4: trimmed, inner spaces removed and upper-cased, so ``mmc 2010/ 123`` matches."""
    cleaned = _SPACES.sub("", number).upper()
    if not cleaned:
        raise InvalidValue(field, "must not be empty")
    if len(cleaned) > 50:
        raise InvalidValue(field, "must be at most 50 characters")
    return cleaned


@dataclass(frozen=True, slots=True)
class DoctorInput:
    name: str
    qualification: str
    council: str
    registration_number: str
    is_owner: bool = False


@dataclass(frozen=True, slots=True)
class ApplicationInput:
    """What the form sends (R1-R4), before anything is checked."""

    kind: ApplicationKind
    clinic_name: str
    address_line: str
    city: str
    state: str
    pincode: str
    clinic_phone: str
    specialties: tuple[str, ...]
    owner_name: str
    owner_phone: str
    owner_email: str
    owner_practises: bool
    doctors: tuple[DoctorInput, ...]


@dataclass(frozen=True, slots=True)
class ApplicationDoctor:
    position: int
    name: str
    qualification: str
    council: str
    registration_number: str
    is_owner: bool
    certificate: Certificate | None = None
    # Set when the application is submitted (from ``IdPort``).
    id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ValidApplication:
    """An input that passed R2-R5; the certificates are checked separately (R7)."""

    kind: ApplicationKind
    clinic_name: str
    address_line: str
    city: str
    state: str
    pincode: str
    clinic_phone: PhoneNumber
    specialties: tuple[str, ...]
    owner_name: str
    owner_phone: PhoneNumber
    owner_email: EmailAddress
    owner_practises: bool
    doctors: tuple[ApplicationDoctor, ...]


def validate(data: ApplicationInput) -> ValidApplication:
    """R2-R5: the shape and values of an application; ``InvalidValue`` names the field."""
    doctors = _doctors(data)
    specialties = tuple(dict.fromkeys(s.strip() for s in data.specialties if s.strip()))
    if not 1 <= len(specialties) <= MAX_SPECIALTIES:
        raise InvalidValue("specialties", f"choose 1-{MAX_SPECIALTIES}")
    for index, specialty in enumerate(specialties):
        if not is_specialty(specialty):
            raise InvalidValue(f"specialties.{index}", "is not on the list")
    pincode = data.pincode.strip()
    if not _PINCODE.fullmatch(pincode):
        raise InvalidValue("pincode", "must be six digits, not starting with 0")
    owner_phone = PhoneNumber.parse(data.owner_phone, field="owner_phone")
    if not _INDIAN_MOBILE.fullmatch(owner_phone.e164):
        raise InvalidValue("owner_phone", "must be an Indian mobile number")
    return ValidApplication(
        kind=data.kind,
        clinic_name=required_text(data.clinic_name, "clinic_name", max_length=200),
        address_line=required_text(data.address_line, "address_line", max_length=300),
        city=required_text(data.city, "city", max_length=100),
        state=required_text(data.state, "state", max_length=100),
        pincode=pincode,
        clinic_phone=PhoneNumber.parse(data.clinic_phone, field="clinic_phone"),
        specialties=specialties,
        owner_name=required_text(data.owner_name, "owner_name", max_length=200),
        owner_phone=owner_phone,
        owner_email=EmailAddress.parse(data.owner_email, field="owner_email"),
        owner_practises=data.owner_practises,
        doctors=doctors,
    )


def _doctors(data: ApplicationInput) -> tuple[ApplicationDoctor, ...]:
    count = len(data.doctors)
    if data.kind is ApplicationKind.SOLO_DOCTOR:
        if count != 1:
            raise InvalidValue("doctors", "a doctor with their own practice lists exactly one")
        if not data.owner_practises or not data.doctors[0].is_owner:
            raise InvalidValue("doctors.1.is_owner", "the one doctor is the owner")
    elif not 1 <= count <= MAX_DOCTORS:
        raise InvalidValue("doctors", f"list 1-{MAX_DOCTORS} doctors")
    owners = sum(1 for d in data.doctors if d.is_owner)
    if data.owner_practises and owners != 1:
        raise InvalidValue("doctors", "mark exactly one doctor as the owner")
    if not data.owner_practises and owners != 0:
        raise InvalidValue("doctors", "no doctor is the owner unless the owner practises")
    seen: set[tuple[str, str]] = set()
    result: list[ApplicationDoctor] = []
    for position, d in enumerate(data.doctors, start=1):
        prefix = f"doctors.{position}"
        council = d.council.strip()
        if not is_council(council):
            raise InvalidValue(f"{prefix}.council", "is not on the list")
        number = normalise_registration(d.registration_number, f"{prefix}.registration_number")
        if (council, number) in seen:
            raise InvalidValue(f"{prefix}.registration_number", "is listed twice")
        seen.add((council, number))
        result.append(
            ApplicationDoctor(
                position=position,
                name=required_text(d.name, f"{prefix}.name", max_length=200),
                qualification=required_text(
                    d.qualification, f"{prefix}.qualification", max_length=200
                ),
                council=council,
                registration_number=number,
                is_owner=d.is_owner,
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ClinicApplication:
    """One application. Build with ``ClinicApplication.submit``; the constructor rehydrates."""

    id: UUID
    reference: str
    kind: ApplicationKind
    status: ApplicationStatus
    clinic_name: str
    address_line: str
    city: str
    state: str
    pincode: str
    clinic_phone: PhoneNumber
    specialties: tuple[str, ...]
    owner_name: str
    owner_phone: PhoneNumber
    owner_email: EmailAddress
    owner_practises: bool
    doctors: tuple[ApplicationDoctor, ...]
    submitted_at: datetime
    updated_at: datetime
    ip_hash: str | None = None
    email_verified_at: datetime | None = None
    confirm_digest: str | None = None
    # R17: other applications' references (or "clinic:<id>") with the same registration.
    duplicate_of: tuple[str, ...] = field(default_factory=tuple)
    # M6c-P2 (R27, R33): who took it and how it was decided.
    taken_by: UUID | None = None
    taken_at: datetime | None = None
    decided_by: UUID | None = None
    decided_at: datetime | None = None
    decision_reason: RejectReason | None = None
    decision_message: str | None = None
    # P3 (R41): the clinic an approval created.
    clinic_id: UUID | None = None

    @property
    def possible_duplicate(self) -> bool:
        return bool(self.duplicate_of)

    @property
    def confirm_expires_at(self) -> datetime:
        return self.submitted_at + CONFIRM_TTL

    @property
    def is_confirmed(self) -> bool:
        return self.email_verified_at is not None

    @classmethod
    def submit(
        cls,
        *,
        id: UUID,
        reference: str,
        application: ValidApplication,
        certificates: dict[int, Certificate],
        doctor_ids: tuple[UUID, ...],
        now: datetime,
        ip_hash: str | None,
        duplicate_of: tuple[str, ...] = (),
    ) -> ClinicApplication:
        """R9: a new ``PENDING`` application with its email not yet confirmed."""
        now = require_utc(now, "now")
        if len(doctor_ids) != len(application.doctors):
            raise InvalidValue("doctors", "every doctor needs an ID")
        doctors = tuple(
            replace(d, certificate=certificates[d.position], id=doctor_id)
            for d, doctor_id in zip(application.doctors, doctor_ids, strict=True)
        )
        return cls(
            id=id,
            reference=reference,
            kind=application.kind,
            status=ApplicationStatus.PENDING,
            clinic_name=application.clinic_name,
            address_line=application.address_line,
            city=application.city,
            state=application.state,
            pincode=application.pincode,
            clinic_phone=application.clinic_phone,
            specialties=application.specialties,
            owner_name=application.owner_name,
            owner_phone=application.owner_phone,
            owner_email=application.owner_email,
            owner_practises=application.owner_practises,
            doctors=doctors,
            submitted_at=now,
            updated_at=now,
            ip_hash=ip_hash,
            duplicate_of=tuple(dict.fromkeys(duplicate_of)),
        )

    def with_confirm_digest(self, digest: str, *, now: datetime) -> ClinicApplication:
        """A (new) confirmation link for an unconfirmed application; the old one stops working."""
        if self.is_confirmed or self.status is not ApplicationStatus.PENDING:
            raise InvalidTransition("application", self.status, "send a confirmation link")
        return replace(self, confirm_digest=digest, updated_at=require_utc(now, "now"))

    def confirm(self, *, now: datetime) -> ClinicApplication:
        """R12: the owner opened the link in time; the link is spent."""
        now = require_utc(now, "now")
        if self.is_confirmed or self.confirm_digest is None or now >= self.confirm_expires_at:
            raise ConfirmInvalid()
        return replace(self, email_verified_at=now, confirm_digest=None, updated_at=now)

    def start_review(self, *, reviewer_id: UUID, now: datetime) -> ClinicApplication:
        """R27: a reviewer takes a confirmed application; a second one is ``AlreadyTaken``."""
        if self.status is ApplicationStatus.UNDER_REVIEW:
            raise AlreadyTaken()
        if self.status is not ApplicationStatus.PENDING or not self.is_confirmed:
            raise InvalidTransition("application", self.status, "start reviewing")
        now = require_utc(now, "now")
        return replace(
            self,
            status=ApplicationStatus.UNDER_REVIEW,
            taken_by=reviewer_id,
            taken_at=now,
            updated_at=now,
        )

    def reject(
        self, *, reviewer_id: UUID, reason: RejectReason, message: str | None, now: datetime
    ) -> ClinicApplication:
        """R33: from ``UNDER_REVIEW`` only, with a reason; ``OTHER`` needs a message."""
        if self.status is not ApplicationStatus.UNDER_REVIEW:
            raise NotUnderReview()
        clean = message.strip() if message else None
        if clean is not None and len(clean) > MAX_MESSAGE:
            raise InvalidValue("message", f"must be at most {MAX_MESSAGE} characters")
        if reason is RejectReason.OTHER and not clean:
            raise InvalidValue("message", "is required when the reason is OTHER")
        now = require_utc(now, "now")
        return replace(
            self,
            status=ApplicationStatus.REJECTED,
            decided_by=reviewer_id,
            decided_at=now,
            decision_reason=reason,
            decision_message=clean or None,
            updated_at=now,
        )

    def approve(
        self, *, reviewer_id: UUID, clinic_id: UUID, verified: set[UUID], now: datetime
    ) -> ClinicApplication:
        """P3 (R41): from ``UNDER_REVIEW``, every doctor verified; records the new clinic."""
        if self.status is not ApplicationStatus.UNDER_REVIEW:
            raise NotUnderReview()
        if any(d.id not in verified for d in self.doctors):
            raise InvalidValue("doctors", "every doctor must be verified before approval")
        now = require_utc(now, "now")
        return replace(
            self,
            status=ApplicationStatus.APPROVED,
            decided_by=reviewer_id,
            decided_at=now,
            clinic_id=clinic_id,
            updated_at=now,
        )

    def doctor(self, doctor_id: UUID) -> ApplicationDoctor:
        for d in self.doctors:
            if d.id == doctor_id:
                return d
        raise NotFound("application doctor")


def format_reference(year: int, number: int) -> str:
    """``MA-2026-0042``: at least four digits, more when the year passes 9999 applications."""
    return f"MA-{year}-{number:04d}"
