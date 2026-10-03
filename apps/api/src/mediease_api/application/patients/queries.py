"""Reading patients: by ID, and the lookup box (FR-PAT-04; spec R5).

Every read is scoped to the request's clinic (NFR-08): another clinic's patient is not
forbidden but absent, so the answer is ``REQ_NOT_FOUND`` and its existence stays hidden.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import structlog

from mediease_api.application.context import RequestContext
from mediease_api.application.patients.views import PatientView
from mediease_api.domain.patients.lookup import MAX_RESULTS, QueryKind, classify_query
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class GetPatient:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext, patient_id: UUID) -> PatientView:
        with self._uow as uow:
            clinic = uow.clinics.get(ctx.clinic_id)
            patient = uow.tenant(ctx.clinic_id).patients.get(patient_id)
            if clinic is None or patient is None:
                logger.info(
                    "tenancy.not_found",
                    entity="patient",
                    entity_id=str(patient_id),
                    clinic_id=str(ctx.clinic_id),
                )
                raise NotFound("patient")
            return PatientView.of(patient, local_date(self._clock.now(), clinic.timezone))


class LookupPatients:
    """Phone, then code, then name prefix; at most 20, ordered by name (spec R5)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext, text: str) -> Sequence[PatientView]:
        parsed = classify_query(text)
        if parsed is None or parsed.value is None:
            return []  # blank, or phone-shaped text that is not a number: matches nobody
        with self._uow as uow:
            clinic = uow.clinics.get(ctx.clinic_id)
            if clinic is None:  # pragma: no cover - the request context names an existing clinic
                raise NotFound("clinic")
            patients = uow.tenant(ctx.clinic_id).patients
            found: Sequence[Patient]
            if parsed.kind is QueryKind.PHONE:
                found = patients.find_by_phone(PhoneNumber(parsed.value), limit=MAX_RESULTS)
            elif parsed.kind is QueryKind.CODE:
                match = patients.get_by_code(parsed.value)
                found = [match] if match is not None else []
            else:
                found = patients.search_by_name_prefix(parsed.value, limit=MAX_RESULTS)
            today = local_date(self._clock.now(), clinic.timezone)
            # The kind only: the text itself is a name or a number and stays out of the log.
            logger.info("patient.lookup", kind=parsed.kind.value, results=len(found))
            return [PatientView.of(p, today) for p in found]
