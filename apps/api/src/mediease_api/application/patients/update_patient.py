"""UpdatePatient — correct a patient's demographics (FR-PAT-01; spec R3, R7).

Only the fields sent change. The code never does. The audit row lists the *names* of the
fields that actually changed, never their values (spec D5): a name or phone number has no
business in an append-only table. An edit that changes nothing records nothing.

Editing a phone does not run the duplicate check: that is about registering, and a
correction that lands on a family's shared number is normal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.patients.views import PatientView
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.patients.patient import Language, Sex, parse_phone
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "patient"


@dataclass(frozen=True, slots=True, repr=False)
class UpdatePatientCommand:
    """``None`` leaves a field alone; a blank ``guardian_name`` clears it (refused for a minor)."""

    patient_id: UUID
    full_name: str | None = None
    phone: str | None = None
    sex: Sex | None = None
    date_of_birth: date | None = None
    age_years: int | None = None
    guardian_name: str | None = None
    language: Language | None = None

    def __repr__(self) -> str:
        return f"UpdatePatientCommand(patient_id={self.patient_id})"


class UpdatePatient:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, cmd: UpdatePatientCommand) -> PatientView:
        phone = parse_phone(cmd.phone) if cmd.phone is not None else None
        with self._uow as uow:
            clinic = uow.clinics.get(ctx.clinic_id)
            if clinic is None:  # pragma: no cover - the request context names an existing clinic
                raise NotFound("clinic")
            patients = uow.tenant(ctx.clinic_id).patients
            patient = patients.get(cmd.patient_id)
            if patient is None:
                logger.info(
                    "tenancy.not_found",
                    entity="patient",
                    entity_id=str(cmd.patient_id),
                    clinic_id=str(ctx.clinic_id),
                )
                raise NotFound("patient")

            now = self._clock.now()
            today = local_date(now, clinic.timezone)
            changed = patient.update_details(
                today=today,
                now=now,
                full_name=cmd.full_name,
                phone=phone,
                sex=cmd.sex,
                date_of_birth=cmd.date_of_birth,
                age_years=cmd.age_years,
                guardian_name=cmd.guardian_name,
                language=cmd.language,
            )
            if changed:
                patients.update(patient)
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.PATIENT_UPDATED,
                    actor=Actor.staff(ctx),
                    now=now,
                    clinic_id=ctx.clinic_id,
                    entity_type=ENTITY_TYPE,
                    entity_id=patient.id,
                    metadata={"fields": ",".join(changed)},
                )
                uow.commit()
            view = PatientView.of(patient, today)

        if changed:
            logger.info(
                "patient.updated",
                clinic_id=str(ctx.clinic_id),
                patient_id=str(patient.id),
                fields=changed,
            )
        return view
