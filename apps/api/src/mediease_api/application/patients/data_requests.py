"""Patient data requests (M9-P3; RUNBOOK §12, §43): export one patient's record, or erase them.

Run by MediEase support from ``delivery/cli/patient_data.py`` on the clinic owner's written
request; the clinic is the Data Fiduciary and answers the patient. Both are audited on the
clinic's log (SYSTEM: the command has no session), with the patient's code and counts only.

- **Export (R1):** the patient's rows from every table that holds them, as JSON, with the stored
  prescription PDFs and the visit reports. The archive is written and protected by the command.
- **Erase (R2-R5):** refused while the patient has an upcoming appointment or an open booking
  request (the clinic settles those first), and for a patient already erased. Then, in one
  transaction, the patient is anonymised (``adapters/db/patient_data.py`` lists what goes and
  what the clinic keeps), and the stored PDFs that printed their details are removed after the
  commit.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import structlog

from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.patient_data import ErasureBlockers, PatientRef
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

FORMAT = "mediease-patient-export/1"


class DataRequestRefused(Exception):
    """The request cannot be carried out; ``reason`` says why, in words for the operator."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True, slots=True)
class PatientExport:
    ref: PatientRef
    record_json: bytes
    files: Mapping[str, bytes]
    missing: Sequence[str]  # files recorded but not in storage


@dataclass(frozen=True, slots=True)
class ErasureOutcome:
    ref: PatientRef
    counts: Mapping[str, int]
    pdfs_removed: int


def _find(uow: UnitOfWork, clinic_slug: str, code: str) -> PatientRef:
    ref = uow.patient_data.find(clinic_slug.strip().lower(), code.strip().upper())
    if ref is None:
        raise DataRequestRefused("not_found", "no patient with that code in that clinic")
    return ref


class ExportPatientData:
    def __init__(
        self, *, uow: UnitOfWork, storage: BlobStoragePort, clock: ClockPort, ids: IdPort
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._clock = clock
        self._ids = ids

    def execute(self, clinic_slug: str, code: str) -> PatientExport:
        with self._uow as uow:
            ref = _find(uow, clinic_slug, code)
            record = uow.patient_data.record(ref)
            files: dict[str, bytes] = {}
            missing: list[str] = []
            for name, key in record.files.items():
                data = self._storage.get(key)
                if data is None:
                    missing.append(name)
                else:
                    files[name] = data
            now = self._clock.now()
            document = {
                "format": FORMAT,
                "exported_at": now.isoformat(),
                "clinic": ref.clinic_slug,
                "patient_code": ref.code,
                "note": (
                    "Everything MediEase stores about this patient for this clinic. Each key is a "
                    "table; files are in the prescriptions/ and reports/ folders."
                ),
                "files_missing_from_storage": missing,
                "tables": record.tables,
            }
            rows = sum(len(v) for v in record.tables.values())
            uow.audit.record(
                AuditEvent.record(
                    id=self._ids.new_id(),
                    action=AuditAction.PATIENT_DATA_EXPORTED,
                    actor_type=ActorType.SYSTEM,
                    now=now,
                    clinic_id=ref.clinic_id,
                    entity_type="patient",
                    entity_id=ref.patient_id,
                    metadata={
                        "code": ref.code,
                        "via": "support_command",
                        "rows": str(rows),
                        "files": str(len(files)),
                    },
                )
            )
            uow.commit()
        logger.info(
            "support.patient_exported",
            patient_id=str(ref.patient_id),
            rows=rows,
            files=len(files),
            missing=len(missing),
        )
        body = json.dumps(document, indent=2, ensure_ascii=False, default=str).encode()
        return PatientExport(ref=ref, record_json=body, files=files, missing=missing)


class ErasePatient:
    def __init__(
        self, *, uow: UnitOfWork, storage: BlobStoragePort, clock: ClockPort, ids: IdPort
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._clock = clock
        self._ids = ids

    def check(self, clinic_slug: str, code: str) -> tuple[PatientRef, ErasureBlockers]:
        """What an erasure would find, without changing anything (the command's first step)."""
        with self._uow as uow:
            ref = _find(uow, clinic_slug, code)
            return ref, self._blockers(uow, ref)

    def _blockers(self, uow: UnitOfWork, ref: PatientRef) -> ErasureBlockers:
        clinic = uow.clinics.get(ref.clinic_id)
        assert clinic is not None  # the patient's foreign key keeps it
        return uow.patient_data.blockers(ref, today=local_date(self._clock.now(), clinic.timezone))

    def execute(self, clinic_slug: str, code: str) -> ErasureOutcome:
        with self._uow as uow:
            ref = _find(uow, clinic_slug, code)
            if ref.already_erased:
                raise DataRequestRefused("already_erased", "this patient has already been erased")
            blockers = self._blockers(uow, ref)
            if blockers.any:
                raise DataRequestRefused(
                    "has_open_bookings",
                    f"the clinic must first cancel {blockers.upcoming_appointments} upcoming "
                    f"appointment(s) and answer {blockers.open_booking_requests} open booking "
                    "request(s) of this patient",
                )
            now = self._clock.now()
            result = uow.patient_data.erase(ref, now=now)
            uow.audit.record(
                AuditEvent.record(
                    id=self._ids.new_id(),
                    action=AuditAction.PATIENT_ERASED,
                    actor_type=ActorType.SYSTEM,
                    now=now,
                    clinic_id=ref.clinic_id,
                    entity_type="patient",
                    entity_id=ref.patient_id,
                    metadata={
                        "code": ref.code,
                        "via": "support_command",
                        **{k: str(v) for k, v in result.counts.items()},
                    },
                )
            )
            uow.commit()
        # After the commit: a failure here leaves a file that is drawn again, not a half erasure.
        removed = 0
        for key in result.blob_keys:
            try:
                if self._storage.exists(key):
                    self._storage.delete(key)
                    removed += 1
            except Exception:
                logger.exception("support.erase_pdf_failed", patient_id=str(ref.patient_id))
        logger.info(
            "support.patient_erased",
            patient_id=str(ref.patient_id),
            pdfs_removed=removed,
            **dict(result.counts),
        )
        return ErasureOutcome(ref=ref, counts=result.counts, pdfs_removed=removed)
