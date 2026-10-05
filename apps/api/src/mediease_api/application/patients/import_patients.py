"""ImportPatients — an ops user loads a clinic's patient list from CSV (FR-PAT-08, FR-OPS-02).

Spec patients R8; design in docs/milestones/M2-patients.md (M2-P4, choices 1A and 2A).

A **dry run** (the default) reads the file, checks every row with the registration rules and
compares it with the clinic's patients, and returns a report; it takes no lock and writes
nothing. A **commit** does the same work again inside one transaction, under the clinic row
lock registration takes (R9), so an import and a front-desk registration of the same phone
serialise, and what it imports matches the data as it is at that moment rather than at the
time of the dry run. Any failure imports nothing.

Rows are classified in file order:

- **invalid**: a rule failed; reported with the column and a fixed reason, never imported;
- **already registered**: same phone *and* same name (case and spacing ignored) as an existing
  patient or an earlier row; always skipped, so running a file twice does not double the list;
- **possible duplicate**: the phone is already in the clinic, or on an earlier row; families
  share phones, so it is imported and flagged (choice 1A, as ``confirm_new`` does);
- otherwise imported, with the next code. Consent is false and "not asked" (R8).

Personal data: the report, the log lines and the audit rows carry row numbers, counts,
column names and the new codes, never a name or a phone (spec D5). Ops users cannot browse
patients (spec §2), so a duplicate says how many patients match, not who they are.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

import structlog

from mediease_api.application.audit import audit_event
from mediease_api.application.context import Actor
from mediease_api.application.patients.errors import ImportInvalid
from mediease_api.application.patients.register_patient import ENTITY_TYPE, record_first_patient
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import AuditEvent
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.patients.import_row import (
    ImportRow,
    header_problems,
    name_key,
    normalise_heading,
    parse_row,
)
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.shared.errors import InvalidValue, NotFound
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

MAX_ROWS = 5_000
# The report's lists stop here; the counts are always complete.
MAX_LISTED = 500
_HEADER_ROW = 1
EXTRA_CELLS_REASON = "has more cells than the header"


class DuplicateKind(StrEnum):
    EXISTING_PATIENT = "existing_patient"
    EARLIER_ROW = "earlier_row"
    ALREADY_REGISTERED = "already_registered"


@dataclass(frozen=True, slots=True)
class RowError:
    row: int
    field: str
    reason: str


@dataclass(frozen=True, slots=True)
class RowDuplicate:
    row: int
    kind: DuplicateKind
    # existing_patient / already_registered: how many of the clinic's patients match.
    matches: int | None = None
    # earlier_row / already_registered within the file: the first row with that phone.
    same_as_row: int | None = None


@dataclass(frozen=True, slots=True)
class ImportReport:
    dry_run: bool
    rows: int
    valid: int
    invalid: int
    possible_duplicates: int
    already_registered: int
    imported: int
    codes: tuple[str, ...]
    errors: tuple[RowError, ...]
    duplicates: tuple[RowDuplicate, ...]
    errors_truncated: bool
    duplicates_truncated: bool


@dataclass(frozen=True, slots=True, repr=False)
class ImportPatientsCommand:
    data: bytes
    dry_run: bool = True

    def __repr__(self) -> str:
        return f"ImportPatientsCommand(<{len(self.data)} bytes>, dry_run={self.dry_run})"


@dataclass(slots=True)
class _Plan:
    """The classification of every row; ``to_import`` keeps file order."""

    rows: int = 0
    errors: list[RowError] = field(default_factory=list)
    duplicates: list[RowDuplicate] = field(default_factory=list)
    to_import: list[ImportRow] = field(default_factory=list)
    flagged: int = 0
    skipped: int = 0

    @property
    def valid(self) -> int:
        return self.rows - len(self.errors)


class ImportPatients:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, *, clinic_id: UUID, actor: Actor, cmd: ImportPatientsCommand) -> ImportReport:
        records = read_rows(cmd.data)  # pure, and before any lock: a bad file costs nothing
        with self._uow as uow:
            clinic = uow.clinics.get(clinic_id, for_update=not cmd.dry_run)
            if clinic is None:
                raise NotFound("clinic")
            now = self._clock.now()
            today = local_date(now, clinic.timezone)
            plan = self._plan(uow, clinic_id, records, today)

            if cmd.dry_run:
                report = _report(plan, dry_run=True, codes=())
                logger.info("patient.import_dry_run", clinic_id=str(clinic_id), **_counts(report))
                return report

            codes = self._import(uow, clinic, actor, plan.to_import, today=today, now=now)
            uow.commit()

        report = _report(plan, dry_run=False, codes=codes)
        logger.info("patient.import_committed", clinic_id=str(clinic_id), **_counts(report))
        return report

    def _plan(
        self, uow: UnitOfWork, clinic_id: UUID, records: Sequence[_Record], today: date
    ) -> _Plan:
        plan = _Plan(rows=len(records))
        parsed: list[tuple[int, ImportRow]] = []
        for record in records:
            if record.extra_cells:
                plan.errors.append(RowError(record.number, "row", EXTRA_CELLS_REASON))
                continue
            try:
                parsed.append((record.number, parse_row(record.cells, today=today)))
            except InvalidValue as exc:
                plan.errors.append(RowError(record.number, exc.field, exc.reason))

        existing = uow.tenant(clinic_id).patients.find_by_phones({row.phone for _, row in parsed})
        on_phone: dict[str, list[str]] = {}
        for patient in existing:
            on_phone.setdefault(patient.phone.e164, []).append(name_key(patient.full_name))

        first_row_for_phone: dict[str, int] = {}
        first_row_for_person: dict[tuple[str, str], int] = {}
        for number, row in parsed:
            phone, person = row.phone.e164, (row.phone.e164, row.name_key)
            known = on_phone.get(phone, [])
            if row.name_key in known:
                plan.skipped += 1
                plan.duplicates.append(
                    RowDuplicate(number, DuplicateKind.ALREADY_REGISTERED, matches=len(known))
                )
            elif person in first_row_for_person:
                plan.skipped += 1
                plan.duplicates.append(
                    RowDuplicate(
                        number,
                        DuplicateKind.ALREADY_REGISTERED,
                        same_as_row=first_row_for_person[person],
                    )
                )
            else:
                if known:
                    plan.flagged += 1
                    plan.duplicates.append(
                        RowDuplicate(number, DuplicateKind.EXISTING_PATIENT, matches=len(known))
                    )
                elif phone in first_row_for_phone:
                    plan.flagged += 1
                    plan.duplicates.append(
                        RowDuplicate(
                            number,
                            DuplicateKind.EARLIER_ROW,
                            same_as_row=first_row_for_phone[phone],
                        )
                    )
                plan.to_import.append(row)
            first_row_for_phone.setdefault(phone, number)
            first_row_for_person.setdefault(person, number)
        return plan

    def _import(
        self,
        uow: UnitOfWork,
        clinic: Clinic,
        actor: Actor,
        rows: Sequence[ImportRow],
        *,
        today: date,
        now: datetime,
    ) -> tuple[str, ...]:
        if not rows:
            return ()
        import_id = str(self._ids.new_id())
        patients: list[Patient] = []
        events: list[AuditEvent] = []
        for row in rows:
            code = clinic.allocate_patient_code(now=now)
            patient = Patient.create(
                id=self._ids.new_id(),
                clinic_id=clinic.id,
                code=code,
                full_name=row.full_name,
                phone=row.phone,
                sex=row.sex,
                registered_on=today,
                created_by=actor.user_id,
                now=now,
                date_of_birth=row.date_of_birth,
                age_years=row.age_years,
                guardian_name=row.guardian_name,
                language=row.language,
            )
            patients.append(patient)
            events.append(
                audit_event(
                    event_id=self._ids.new_id(),
                    action=AuditAction.PATIENT_IMPORTED,
                    actor=actor,
                    now=now,
                    clinic_id=clinic.id,
                    entity_type=ENTITY_TYPE,
                    entity_id=patient.id,
                    metadata={"code": code, "import_id": import_id},
                )
            )
        # Two batched inserts instead of 2 x 5,000 round trips; same transaction (R11).
        uow.tenant(clinic.id).patients.add_many(patients)
        uow.audit.record_many(events)
        uow.clinics.update(clinic)
        record_first_patient(uow, self._ids, clinic.id, now)
        return tuple(p.code for p in patients)


# --- reading the file --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, repr=False)
class _Record:
    """One data row: its spreadsheet row number (the header is row 1) and cells by column."""

    number: int
    cells: dict[str, str]
    extra_cells: bool = False


def read_rows(data: bytes) -> list[_Record]:
    """Decode and split the file, check the header, and return the non-blank data rows.

    Raises ``ImportInvalid`` for anything that makes the file as a whole unusable.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportInvalid(["the file is not UTF-8 text (save it as CSV UTF-8)"]) from None

    lines = _csv_records(text)
    first = next(lines, None)
    if first is None:
        raise ImportInvalid(["the file is empty"])
    _, header = first
    problems = header_problems(header)
    if problems:
        raise ImportInvalid(problems)
    columns = [normalise_heading(cell) for cell in header]

    records: list[_Record] = []
    for number, cells in lines:
        if not any(cell.strip() for cell in cells):
            continue  # spreadsheets leave empty rows at the end
        if len(records) == MAX_ROWS:
            raise ImportInvalid([f"the file has more than {MAX_ROWS} data rows; split it"])
        padded = [*cells, *([""] * (len(columns) - len(cells)))]
        # A cell beyond the last column is data we would silently drop: the row is refused.
        extra = any(cell.strip() for cell in cells[len(columns) :])
        records.append(_Record(number, dict(zip(columns, padded, strict=False)), extra))
    if not records:
        raise ImportInvalid(["the file has no data rows"])
    return records


def _csv_records(text: str) -> Iterator[tuple[int, list[str]]]:
    """``(row number, cells)`` per CSV record; the header is row 1."""
    # strict: a stray or unterminated quote is an error, not a cell that swallows the file.
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    number = _HEADER_ROW - 1
    while True:
        try:
            cells = next(reader)
        except StopIteration:
            return
        except csv.Error:
            raise ImportInvalid([f"the file is not valid CSV near row {number + 1}"]) from None
        number += 1
        yield number, cells


# --- the report --------------------------------------------------------------------------------


def _report(plan: _Plan, *, dry_run: bool, codes: tuple[str, ...]) -> ImportReport:
    return ImportReport(
        dry_run=dry_run,
        rows=plan.rows,
        valid=plan.valid,
        invalid=len(plan.errors),
        possible_duplicates=plan.flagged,
        already_registered=plan.skipped,
        imported=len(codes),
        codes=codes,
        errors=tuple(plan.errors[:MAX_LISTED]),
        duplicates=tuple(plan.duplicates[:MAX_LISTED]),
        errors_truncated=len(plan.errors) > MAX_LISTED,
        duplicates_truncated=len(plan.duplicates) > MAX_LISTED,
    )


def _counts(report: ImportReport) -> dict[str, int]:
    return {
        "rows": report.rows,
        "valid": report.valid,
        "invalid": report.invalid,
        "possible_duplicates": report.possible_duplicates,
        "already_registered": report.already_registered,
        "imported": report.imported,
    }
