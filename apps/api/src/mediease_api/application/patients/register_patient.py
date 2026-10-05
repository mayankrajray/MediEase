"""RegisterPatient — add a patient to the clinic (FR-PAT-01..03; spec R1-R4, R9, R10).

The order inside the transaction is the design (spec R9):

1. **Lock the clinic row.** A second registration for this clinic waits here. When it gets
   in, the first one's patient is committed and visible to the duplicate check below, so two
   staff members registering the same new phone cannot both pass it (AC6).
2. **Check the phone** before taking a number. A refused registration (``PAT_PHONE_EXISTS``)
   leaves the counter untouched and the transaction rolls back, so refusals spend no code.
3. **Take the next code**, create the patient, save the counter, audit, commit. Codes are
   therefore unique and gap-free except for rolled-back transactions (AC3).

The phone is not unique: families share one. ``confirm_new`` is how the front desk says "yes,
a second person on this number".

Personal data: the audit row and the log lines carry the code and counts, never a name or a
phone number (spec D5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.patients.errors import MAX_CANDIDATES, PhoneExists
from mediease_api.application.patients.views import CandidateView, PatientView
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.patients.patient import Language, Patient, Sex, parse_phone
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "patient"


@dataclass(frozen=True, slots=True, repr=False)
class RegisterPatientCommand:
    full_name: str
    phone: str
    sex: Sex
    date_of_birth: date | None = None
    age_years: int | None = None
    guardian_name: str | None = None
    language: Language = Language.EN
    confirm_new: bool = False

    def __repr__(self) -> str:
        return "RegisterPatientCommand(<redacted>)"


class RegisterPatient:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, cmd: RegisterPatientCommand) -> PatientView:
        phone = parse_phone(cmd.phone)  # pure: before any lock is taken
        with self._uow as uow:
            clinic = uow.clinics.get(ctx.clinic_id, for_update=True)
            if clinic is None:  # pragma: no cover - the request context names an existing clinic
                raise NotFound("clinic")
            now = self._clock.now()
            today = local_date(now, clinic.timezone)
            patients = uow.tenant(ctx.clinic_id).patients

            existing = patients.find_by_phone(phone, limit=MAX_CANDIDATES)
            if existing and not cmd.confirm_new:
                # A count only: the names are for the response, not the log (spec D5).
                logger.info(
                    "patient.duplicate_phone_offered",
                    clinic_id=str(ctx.clinic_id),
                    candidates=len(existing),
                )
                raise PhoneExists([CandidateView.of(p, today) for p in existing])

            code = clinic.allocate_patient_code(now=now)
            patient = Patient.create(
                id=self._ids.new_id(),
                clinic_id=ctx.clinic_id,
                code=code,
                full_name=cmd.full_name,
                phone=phone,
                sex=cmd.sex,
                registered_on=today,
                created_by=ctx.user_id,
                now=now,
                date_of_birth=cmd.date_of_birth,
                age_years=cmd.age_years,
                guardian_name=cmd.guardian_name,
                language=cmd.language,
            )
            patients.add(patient)
            uow.clinics.update(clinic)
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.PATIENT_CREATED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=patient.id,
                metadata={
                    "code": code,
                    "confirmed_shared_phone": "true" if existing else "false",
                },
            )
            record_first_patient(uow, self._ids, ctx.clinic_id, now)
            view = PatientView.of(patient, today)
            uow.commit()

        logger.info(
            "patient.created",
            clinic_id=str(ctx.clinic_id),
            patient_id=str(patient.id),
            code=patient.code,
        )
        return view


def record_first_patient(uow: UnitOfWork, ids: IdPort, clinic_id: UUID, now: datetime) -> None:
    """The onboarding checklist's first-patient time (FR-OPS-04); later ones never move it.

    Registration and the ops import (M2-P4) both call it, whichever comes first.
    """
    checklist = uow.tenant(clinic_id).checklist
    recorded = checklist.get()
    if recorded is None:
        recorded = OnboardingChecklist.start(id=ids.new_id(), clinic_id=clinic_id, now=now)
        recorded.record(OnboardingStep.PATIENTS_IMPORTED, now=now)
        checklist.add(recorded)
        return
    if recorded.record(OnboardingStep.PATIENTS_IMPORTED, now=now):
        checklist.update(recorded)
