"""Patient data requests (M9-P3; RUNBOOK §12, §43): one patient's whole record, and its erasure.

A reviewed cross-table reader and writer, always bound to one clinic and one patient. It exists
for the support command that answers a clinic owner's written request (the clinic is the Data
Fiduciary, MediEase the processor): the patient's right to their data, and to erasure.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

Row = Mapping[str, Any]  # one table row, JSON-ready (IDs, dates and times as strings)


@dataclass(frozen=True, slots=True)
class PatientRef:
    clinic_id: UUID
    clinic_slug: str
    patient_id: UUID
    code: str
    already_erased: bool


@dataclass(frozen=True, slots=True)
class PatientRecord:
    """Everything stored about the patient in the clinic, by table, and the files to include."""

    tables: Mapping[str, Sequence[Row]]
    # file name in the archive -> blob key
    files: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ErasureBlockers:
    """R2: what must be settled first, so that nothing still needs to reach the patient."""

    upcoming_appointments: int
    open_booking_requests: int

    @property
    def any(self) -> bool:
        return bool(self.upcoming_appointments or self.open_booking_requests)


@dataclass(frozen=True, slots=True)
class ErasureResult:
    counts: Mapping[str, int]
    # Stored PDFs that printed the patient's details; removed after the commit. Each is drawn
    # again from the anonymised row if the clinic downloads it.
    blob_keys: Sequence[str]


class PatientDataStore(Protocol):
    def find(self, clinic_slug: str, code: str) -> PatientRef | None:
        """The clinic's patient with this code (exact, canonical), or None."""
        ...

    def record(self, ref: PatientRef) -> PatientRecord: ...

    def blockers(self, ref: PatientRef, *, today: date) -> ErasureBlockers: ...

    def erase(self, ref: PatientRef, *, now: datetime) -> ErasureResult:
        """Anonymise the patient and remove their contact data, in the caller's transaction."""
        ...
