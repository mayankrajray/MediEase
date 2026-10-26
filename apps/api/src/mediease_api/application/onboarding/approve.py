"""Approving an application, and verifying ops-created clinics (M6c-P3; FR-ONB-04, 06, 08).

``ApproveApplication`` is the one creation path (FR-ONB-08): in **one transaction** it runs the
same rule sets as the ops wizard (``CreateClinic``, ``AddDoctor``, ``InviteStaff`` through their
``in_transaction``), records the clinic and every doctor as verified against the application, and
marks the application ``APPROVED``. A failure anywhere (a slug taken, an owner who already works
there) leaves nothing behind. The clinic starts ``ONBOARDING`` and becomes ``ACTIVE`` when the
owner accepts the emailed invitation (D1).

``VerifyDoctor`` and ``VerifyClinic`` record a reviewer's checks of an ops-created clinic
(FR-ONB-06): unverified until then, never verified by being created.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.clinics.invite_staff import (
    InviteDelivery,
    InviteStaff,
    InviteStaffCommand,
)
from mediease_api.application.clinics.onboard_clinic import (
    AddDoctor,
    CreateClinic,
    CreateClinicCommand,
    DoctorCommand,
)
from mediease_api.application.context import Actor
from mediease_api.application.onboarding.review import ApplicationDetail, load_application
from mediease_api.application.onboarding.submit import ENTITY
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.verification import VerificationSource
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.onboarding.application import ApplicationKind, CheckResult
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.subscriptions.subscription import plan_for_application
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import InviteSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ApproveCommand:
    """R42: what the reviewer chooses on the prefilled form; the rest is the application's."""

    slug: str
    booking_mode: BookingMode = BookingMode.TOKENS
    timezone: str = "Asia/Kolkata"
    # Corrections of the clinic's own details (None keeps the application's).
    clinic_name: str | None = None
    address_line: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None


@dataclass(frozen=True, slots=True)
class Approval:
    detail: ApplicationDetail
    clinic: Clinic
    delivery: InviteDelivery


class ApproveApplication:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: InviteSecrets
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def execute(self, actor: Actor, application_id: UUID, cmd: ApproveCommand) -> Approval:
        create = CreateClinic(uow=self._uow, clock=self._clock, ids=self._ids)
        add = AddDoctor(uow=self._uow, clock=self._clock, ids=self._ids)
        invite = InviteStaff(uow=self._uow, clock=self._clock, ids=self._ids, secrets=self._secrets)
        with self._uow as uow:
            now = self._clock.now()
            application = load_application(uow, application_id, lock=True)
            checks = uow.applications.checks(application.id)
            verified = {d for d, c in checks.items() if c.result is CheckResult.VERIFIED}
            if any(d.id not in verified for d in application.doctors):
                raise InvalidValue("doctors", "every doctor must be verified before approval")

            clinic = create.in_transaction(
                uow,
                actor=actor,
                cmd=CreateClinicCommand(
                    name=cmd.clinic_name or application.clinic_name,
                    slug=cmd.slug,
                    timezone=cmd.timezone,
                    phone=application.clinic_phone.e164,
                    address_line=cmd.address_line or application.address_line,
                    city=cmd.city or application.city,
                    state=cmd.state or application.state,
                    pincode=cmd.pincode or application.pincode,
                    specialties=application.specialties,
                    booking_mode=cmd.booking_mode,
                    # M6d-P7 (plans R1): Solo for a solo doctor, else the smallest plan that fits.
                    plan=plan_for_application(
                        solo=application.kind is ApplicationKind.SOLO_DOCTOR,
                        doctors=len(application.doctors),
                    ),
                ),
                now=now,
            )
            clinic.verify(
                by=actor.user_id,
                source=VerificationSource.APPLICATION,
                now=now,
                application_id=application.id,
            )
            uow.clinics.update(clinic)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.CLINIC_VERIFIED,
                actor=actor,
                now=now,
                clinic_id=clinic.id,
                metadata={"source": "APPLICATION", "application_id": str(application.id)},
            )

            doctors = uow.tenant(clinic.id).doctors
            owner_doctor: UUID | None = None
            for d in application.doctors:
                doctor = add.in_transaction(
                    uow,
                    clinic_id=clinic.id,
                    actor=actor,
                    cmd=DoctorCommand(
                        display_name=d.name,
                        qualification=d.qualification,
                        registration_number=d.registration_number,
                        registration_council=d.council,
                    ),
                    now=now,
                )
                doctor.verify(by=actor.user_id, source=VerificationSource.APPLICATION, now=now)
                # M6c-P5 (R60): an applicant asked to be on MediEase, so its doctors are shown;
                # the owner may hide any of them.
                doctor.set_visible(True, now=now)
                doctors.update(doctor)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.DOCTOR_VERIFIED,
                    actor=actor,
                    now=now,
                    clinic_id=clinic.id,
                    entity_type="doctor",
                    entity_id=doctor.id,
                    metadata={"source": "APPLICATION", "application_id": str(application.id)},
                )
                if d.is_owner:
                    owner_doctor = doctor.id

            invitation = invite.in_transaction(
                uow,
                clinic_id=clinic.id,
                actor=actor,
                cmd=InviteStaffCommand(
                    full_name=application.owner_name,
                    role=Role.OWNER,
                    email=application.owner_email.value,
                    phone=application.owner_phone.e164,
                    doctor_id=owner_doctor,
                    email_delivery=True,
                ),
                now=now,
            )
            approved = application.approve(
                reviewer_id=actor.user_id, clinic_id=clinic.id, verified=verified, now=now
            )
            uow.applications.update(approved)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.APPLICATION_APPROVED,
                actor=actor,
                now=now,
                clinic_id=clinic.id,
                entity_type=ENTITY,
                entity_id=application.id,
                metadata={
                    "application_id": str(application.id),
                    "doctors": str(len(application.doctors)),
                },
            )
            detail = ApplicationDetail(approved, checks)
            uow.commit()
        logger.info(
            "application.approved",
            application_id=str(application_id),
            clinic_id=str(clinic.id),
            delivery=invitation.delivery.value,
        )
        return Approval(detail, clinic, invitation.delivery)


class VerifyDoctor:
    """R45: a reviewer's check of an ops-created clinic's doctor (both answers yes)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self,
        actor: Actor,
        clinic_id: UUID,
        doctor_id: UUID,
        *,
        register_checked: bool,
        certificate_matches: bool,
    ) -> bool:
        if not (register_checked and certificate_matches):
            raise InvalidValue("result", "verifying needs the register and the certificate checked")
        with self._uow as uow:
            now = self._clock.now()
            if uow.clinics.get(clinic_id) is None:
                raise NotFound("clinic")
            doctors = uow.tenant(clinic_id).doctors
            doctor = doctors.get(doctor_id)
            if doctor is None:
                raise NotFound("doctor")
            changed = doctor.verify(by=actor.user_id, source=VerificationSource.OPS_CHECK, now=now)
            if changed:
                doctors.update(doctor)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.DOCTOR_VERIFIED,
                    actor=actor,
                    now=now,
                    clinic_id=clinic_id,
                    entity_type="doctor",
                    entity_id=doctor.id,
                    metadata={"source": "OPS_CHECK"},
                )
            uow.commit()
        return changed


class VerifyClinic:
    """R45: verify an ops-created clinic once at least one active doctor is verified."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, actor: Actor, clinic_id: UUID) -> Clinic:
        with self._uow as uow:
            now = self._clock.now()
            clinic = uow.clinics.get(clinic_id, for_update=True)
            if clinic is None:
                raise NotFound("clinic")
            doctors = uow.tenant(clinic_id).doctors.list()
            if not any(d.is_active and d.is_verified for d in doctors):
                raise InvalidValue("doctors", "verify at least one active doctor first")
            if clinic.verify(by=actor.user_id, source=VerificationSource.OPS_CHECK, now=now):
                uow.clinics.update(clinic)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.CLINIC_VERIFIED,
                    actor=actor,
                    now=now,
                    clinic_id=clinic_id,
                    metadata={"source": "OPS_CHECK"},
                )
            uow.commit()
        return clinic
