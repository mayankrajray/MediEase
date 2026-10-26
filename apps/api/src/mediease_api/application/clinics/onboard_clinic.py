"""Onboarding a clinic and keeping its details right (FR-ORG-01, FR-ORG-02, FR-OPS-01/04).

Four use cases, each one transaction with its audit row and its checklist
step (R11, R12):

- ``CreateClinic`` — ops creates a clinic in ``ONBOARDING`` and starts its
  checklist. The slug is unique platform-wide because it appears in public
  links from M7, so a duplicate is refused rather than silently suffixed.
- ``AddDoctor`` — a doctor profile with the registration details every
  prescription must print (I3). Used by ops during onboarding and by the
  owner afterwards; the only difference is the actor.
- ``UpdateDoctor`` — correct the details or link a staff account. A
  ``user_id`` must belong to an active member of this clinic, so a profile
  cannot be attached to a stranger.
- ``UpdateClinic`` — the owner edits their own clinic's details.

The clinic's ID always comes from the caller's authority: the ops path takes
it from the URL (an ops user has no membership to infer it from), the owner
path from the request context. Neither reads it from a body.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.billing.fees import add_default_services
from mediease_api.application.context import Actor
from mediease_api.application.scheduling.booking_mode import check_mode_supported, reconcile_clinic
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.clinic import Clinic, PaperSize
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.membership import MembershipStatus
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

from .errors import SlugTaken

logger = structlog.get_logger(__name__)

CLINIC_ENTITY = "clinic"
DOCTOR_ENTITY = "doctor"


@dataclass(frozen=True, slots=True)
class CreateClinicCommand:
    name: str
    slug: str
    timezone: str | None = None
    phone: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    specialties: tuple[str, ...] = ()
    patient_code_prefix: str | None = None
    booking_mode: BookingMode = BookingMode.TOKENS
    rx_paper_size: PaperSize = PaperSize.A5


@dataclass(frozen=True, slots=True)
class DoctorCommand:
    """New or corrected doctor details; ``None`` leaves a field alone on update."""

    display_name: str | None = None
    qualification: str | None = None
    registration_number: str | None = None
    registration_council: str | None = None
    specialty: str | None = None
    user_id: UUID | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class UpdateClinicCommand:
    name: str | None = None
    timezone: str | None = None
    phone: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    specialties: tuple[str, ...] | None = None
    booking_mode: BookingMode | None = None
    rx_paper_size: PaperSize | None = None
    # M6a-P8 (decision 3A): appointment reminders.
    reminder_evening_before: bool | None = None
    reminder_hours_before: int | None = None
    # M6b-P4: the online-request hold (minutes) and whether the form must ask age and sex.
    request_hold_minutes: int | None = None
    request_requires_age_sex: bool | None = None


class CreateClinic:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, actor: Actor, cmd: CreateClinicCommand) -> Clinic:
        with self._uow as uow:
            clinic = self.in_transaction(uow, actor=actor, cmd=cmd, now=self._clock.now())
            uow.commit()
        return clinic

    def in_transaction(
        self, uow: UnitOfWork, *, actor: Actor, cmd: CreateClinicCommand, now: datetime
    ) -> Clinic:
        """The clinic, its checklist and audit row in the caller's transaction (M6c-P3)."""
        phone = PhoneNumber.parse(cmd.phone, field="phone") if cmd.phone else None
        if uow.clinics.get_by_slug(cmd.slug) is not None:
            raise SlugTaken()

        clinic = Clinic.create(
            id=self._ids.new_id(),
            name=cmd.name,
            slug=cmd.slug,
            now=now,
            timezone=cmd.timezone or "Asia/Kolkata",
            phone=phone,
            address_line=cmd.address_line,
            city=cmd.city,
            state=cmd.state,
            pincode=cmd.pincode,
            specialties=cmd.specialties,
            patient_code_prefix=cmd.patient_code_prefix,
            booking_mode=cmd.booking_mode,
            rx_paper_size=cmd.rx_paper_size,
        )
        uow.clinics.add(clinic)

        checklist = OnboardingChecklist.start(id=self._ids.new_id(), clinic_id=clinic.id, now=now)
        checklist.record(OnboardingStep.CLINIC_CREATED, now=now)
        uow.tenant(clinic.id).checklist.add(checklist)
        # M6d-P1 (R2): every clinic starts with Consultation and Follow-up.
        add_default_services(uow.tenant(clinic.id), clinic.id, self._ids, now)

        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=AuditAction.CLINIC_CREATED,
            actor=actor,
            now=now,
            clinic_id=clinic.id,
            entity_type=CLINIC_ENTITY,
            entity_id=clinic.id,
            metadata={"slug": clinic.slug},
        )

        logger.info("clinic.created", clinic_id=str(clinic.id), slug=clinic.slug)
        return clinic


class AddDoctor:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, *, clinic_id: UUID, actor: Actor, cmd: DoctorCommand) -> Doctor:
        with self._uow as uow:
            doctor = self.in_transaction(
                uow, clinic_id=clinic_id, actor=actor, cmd=cmd, now=self._clock.now()
            )
            uow.commit()
        return doctor

    def in_transaction(
        self,
        uow: UnitOfWork,
        *,
        clinic_id: UUID,
        actor: Actor,
        cmd: DoctorCommand,
        now: datetime,
    ) -> Doctor:
        """The doctor and its audit row in the caller's transaction (M6c-P3)."""
        required = _require_doctor_details(cmd)
        if uow.clinics.get(clinic_id) is None:
            raise NotFound("clinic")
        if cmd.user_id is not None:
            _require_linkable_member(uow, clinic_id, cmd.user_id)

        doctor = Doctor.create(
            id=self._ids.new_id(),
            clinic_id=clinic_id,
            now=now,
            user_id=cmd.user_id,
            specialty=cmd.specialty,
            **required,
        )
        uow.tenant(clinic_id).doctors.add(doctor)
        _record_first_doctor(uow, self._ids, clinic_id, now)
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=AuditAction.DOCTOR_ADDED,
            actor=actor,
            now=now,
            clinic_id=clinic_id,
            entity_type=DOCTOR_ENTITY,
            entity_id=doctor.id,
            metadata={"registration_number": doctor.registration_number},
        )

        logger.info("doctor.added", clinic_id=str(clinic_id), doctor_id=str(doctor.id))
        return doctor


class UpdateDoctor:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self, *, clinic_id: UUID, actor: Actor, doctor_id: UUID, cmd: DoctorCommand
    ) -> Doctor:
        with self._uow as uow:
            now = self._clock.now()
            doctors = uow.tenant(clinic_id).doctors
            doctor = doctors.get(doctor_id)
            if doctor is None:
                logger.info(
                    "tenancy.not_found",
                    entity="doctor",
                    entity_id=str(doctor_id),
                    clinic_id=str(clinic_id),
                )
                raise NotFound("doctor")
            if cmd.user_id is not None:
                _require_linkable_member(uow, clinic_id, cmd.user_id, doctor_id=doctor.id)

            doctor.update_details(
                now=now,
                display_name=cmd.display_name,
                qualification=cmd.qualification,
                registration_number=cmd.registration_number,
                registration_council=cmd.registration_council,
                specialty=cmd.specialty,
                user_id=cmd.user_id,
            )
            changed = _changed_fields(cmd)
            if cmd.is_active is False and doctor.is_active:
                doctor.deactivate(now=now)
            doctors.update(doctor)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.DOCTOR_UPDATED,
                actor=actor,
                now=now,
                clinic_id=clinic_id,
                entity_type=DOCTOR_ENTITY,
                entity_id=doctor.id,
                metadata={"fields": changed, "is_active": str(doctor.is_active).lower()},
            )
            uow.commit()

        logger.info("doctor.updated", clinic_id=str(clinic_id), doctor_id=str(doctor_id))
        return doctor


class UpdateClinic:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, *, clinic_id: UUID, actor: Actor, cmd: UpdateClinicCommand) -> Clinic:
        phone = PhoneNumber.parse(cmd.phone, field="phone") if cmd.phone else None
        with self._uow as uow:
            now = self._clock.now()
            clinic = uow.clinics.get(clinic_id)
            if clinic is None:
                raise NotFound("clinic")

            clinic.update_details(
                now=now,
                name=cmd.name,
                timezone=cmd.timezone,
                phone=phone,
                address_line=cmd.address_line,
                city=cmd.city,
                state=cmd.state,
                pincode=cmd.pincode,
                specialties=cmd.specialties,
                rx_paper_size=cmd.rx_paper_size,
            )
            clinic.change_reminders(
                now=now,
                evening_before=cmd.reminder_evening_before,
                hours_before=cmd.reminder_hours_before,
            )
            clinic.change_booking_requests(
                now=now,
                hold_minutes=cmd.request_hold_minutes,
                requires_age_sex=cmd.request_requires_age_sex,
            )
            if cmd.booking_mode is not None and cmd.booking_mode is not clinic.booking_mode:
                # R19: refused unless every current block supports the new mode.
                today = local_date(now, clinic.timezone)
                check_mode_supported(uow, clinic, cmd.booking_mode, today)
                clinic.change_booking_mode(cmd.booking_mode, now=now)
                uow.clinics.update(clinic)
                reconcile_clinic(uow, clinic, today, now)
            uow.clinics.update(clinic)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.CLINIC_UPDATED,
                actor=actor,
                now=now,
                clinic_id=clinic.id,
                entity_type=CLINIC_ENTITY,
                entity_id=clinic.id,
                metadata={"fields": _changed_fields(cmd)},
            )
            uow.commit()

        logger.info("clinic.updated", clinic_id=str(clinic_id))
        return clinic


def _require_doctor_details(cmd: DoctorCommand) -> dict[str, str]:
    """A new doctor needs every printed field (I3); an update may omit them."""
    required = {
        "display_name": cmd.display_name,
        "qualification": cmd.qualification,
        "registration_number": cmd.registration_number,
        "registration_council": cmd.registration_council,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise InvalidValue(missing[0], "is required for a doctor")
    return {name: value for name, value in required.items() if value is not None}


def _require_linkable_member(
    uow: UnitOfWork, clinic_id: UUID, user_id: UUID, *, doctor_id: UUID | None = None
) -> None:
    """A doctor profile may only be linked to an active member with no profile yet.

    One profile per user per clinic is a database constraint (spec §8); checking
    it here turns a would-be 500 into a field-level 422 the owner can act on.
    """
    membership = uow.tenant(clinic_id).memberships.get_for_user(user_id)
    if membership is None or membership.status is not MembershipStatus.ACTIVE:
        raise InvalidValue("user_id", "must be an active member of this clinic")
    linked = uow.tenant(clinic_id).doctors.get_for_user(user_id)
    if linked is not None and linked.id != doctor_id:
        raise InvalidValue("user_id", "already has a doctor profile in this clinic")


def _record_first_doctor(uow: UnitOfWork, ids: IdPort, clinic_id: UUID, now: datetime) -> None:
    checklist = uow.tenant(clinic_id).checklist
    recorded = checklist.get()
    if recorded is None:
        recorded = OnboardingChecklist.start(id=ids.new_id(), clinic_id=clinic_id, now=now)
        recorded.record(OnboardingStep.DOCTORS_ADDED, now=now)
        checklist.add(recorded)
        return
    if recorded.record(OnboardingStep.DOCTORS_ADDED, now=now):
        checklist.update(recorded)


def _changed_fields(cmd: DoctorCommand | UpdateClinicCommand) -> str:
    """Which fields the caller sent — names only, never the values (audit hygiene)."""
    sent = [f.name for f in fields(cmd) if getattr(cmd, f.name) is not None]
    return ",".join(sent) or "none"
