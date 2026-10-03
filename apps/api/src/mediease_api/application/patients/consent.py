"""Consent, opt-out and opt-in (FR-PAT-05, FR-PAT-06, FR-MSG-05; spec patients R6, AC5).

Three actions, never one form, so an opt-out cannot be undone by re-submitting a screen:

- ``RecordConsent`` — the answer to "may we message you on WhatsApp, on SMS?". Refused while the
  patient is opted out (decision A): ``OptIn`` takes the new consent instead.
- ``OptOut`` — stop all messages. Idempotent: a second opt-out (a patient sending STOP twice)
  changes nothing and records nothing. Takes a ``source`` so M5's inbound STOP handler reuses it.
- ``OptIn`` — the explicit way back, with the consent given on the way.

Each reads the patient ``FOR UPDATE``, so two staff members, or staff and M5's STOP handler, acting
at once cannot leave consent recorded over an opt-out. Each change is an audit row in the same
transaction: consent is evidence (DPDP). The row holds the flags (booleans) and on whose behalf
they were given (``guardian`` for a minor, decision D1), never a name or a phone number.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.patients.views import PatientView
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

ENTITY_TYPE = "patient"


class OptOutSource(StrEnum):
    """Where an opt-out came from: a staff member now, the patient's STOP reply from M5."""

    STAFF = "staff"
    INBOUND_MESSAGE = "inbound_message"


@dataclass(frozen=True, slots=True)
class ConsentCommand:
    patient_id: UUID
    whatsapp: bool
    sms: bool


def _flag(value: bool) -> str:
    return "true" if value else "false"


class _PatientChange:
    """Shared steps: load the patient under a row lock, change it, save, audit, commit."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def _load(self, uow: UnitOfWork, ctx: RequestContext, patient_id: UUID) -> tuple[Patient, str]:
        clinic = uow.clinics.get(ctx.clinic_id)
        patient = uow.tenant(ctx.clinic_id).patients.get(patient_id, for_update=True)
        if clinic is None or patient is None:
            logger.info(
                "tenancy.not_found",
                entity="patient",
                entity_id=str(patient_id),
                clinic_id=str(ctx.clinic_id),
            )
            raise NotFound("patient")
        return patient, clinic.timezone

    def _save(
        self,
        uow: UnitOfWork,
        ctx: RequestContext,
        patient: Patient,
        action: AuditAction,
        metadata: Mapping[str, str],
        now: datetime,
    ) -> None:
        uow.tenant(ctx.clinic_id).patients.update(patient)
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=action,
            actor=Actor.staff(ctx),
            now=now,
            clinic_id=ctx.clinic_id,
            entity_type=ENTITY_TYPE,
            entity_id=patient.id,
            metadata=metadata,
        )


class RecordConsent(_PatientChange):
    def execute(self, ctx: RequestContext, cmd: ConsentCommand) -> PatientView:
        with self._uow as uow:
            patient, timezone = self._load(uow, ctx, cmd.patient_id)
            now = self._clock.now()
            today = local_date(now, timezone)
            patient.record_consent(whatsapp=cmd.whatsapp, sms=cmd.sms, by=ctx.user_id, now=now)
            metadata = {
                "whatsapp": _flag(cmd.whatsapp),
                "sms": _flag(cmd.sms),
                "given_by": patient.consent_given_by(today).value,
            }
            self._save(uow, ctx, patient, AuditAction.PATIENT_CONSENT_CHANGED, metadata, now)
            view = PatientView.of(patient, today)
            uow.commit()
        logger.info(
            "patient.consent_changed", clinic_id=str(ctx.clinic_id), patient_id=str(patient.id)
        )
        return view


class OptOut(_PatientChange):
    def execute(
        self, ctx: RequestContext, patient_id: UUID, source: OptOutSource = OptOutSource.STAFF
    ) -> PatientView:
        with self._uow as uow:
            patient, timezone = self._load(uow, ctx, patient_id)
            now = self._clock.now()
            today = local_date(now, timezone)
            changed = patient.opt_out(now=now)
            if changed:
                self._save(
                    uow, ctx, patient, AuditAction.PATIENT_OPTED_OUT, {"source": source.value}, now
                )
                uow.commit()
            view = PatientView.of(patient, today)
        if changed:
            # Spec §7 analytics event `patient_opted_out`: a log event until M6 counts it.
            logger.info(
                "patient.opted_out",
                clinic_id=str(ctx.clinic_id),
                patient_id=str(patient.id),
                source=source.value,
                analytics="patient_opted_out",
            )
        return view


class OptIn(_PatientChange):
    def execute(self, ctx: RequestContext, cmd: ConsentCommand) -> PatientView:
        with self._uow as uow:
            patient, timezone = self._load(uow, ctx, cmd.patient_id)
            now = self._clock.now()
            today = local_date(now, timezone)
            patient.opt_in(whatsapp=cmd.whatsapp, sms=cmd.sms, by=ctx.user_id, now=now)
            metadata = {
                "whatsapp": _flag(cmd.whatsapp),
                "sms": _flag(cmd.sms),
                "given_by": patient.consent_given_by(today).value,
            }
            self._save(uow, ctx, patient, AuditAction.PATIENT_OPTED_IN, metadata, now)
            view = PatientView.of(patient, today)
            uow.commit()
        logger.info("patient.opted_in", clinic_id=str(ctx.clinic_id), patient_id=str(patient.id))
        return view
