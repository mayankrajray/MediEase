"""Import one clinic, its people and recent history from CSV files (M9-P1 C2; spec clinic-import).

The developer prepares a folder of CSV files (the format is in ``docs/specs/clinic-import.md``;
the bundled demo in ``demo_clinic/`` is a complete, invented example) and runs, on the server:

    python -m mediease_api.delivery.cli.import_clinic --dir /import
    python -m mediease_api.delivery.cli.import_clinic --demo        # the bundled demo clinic

Everything is built through the domain's own rules (the same factories and state changes the use
cases use), back-dated where the data is history: past visits are booked into the doctor's
session of that day, seen, written up, prescribed and billed at their own time. Upcoming
appointments and future follow-ups get their reminders as if booked now.

Safe by construction:

- one transaction: any problem rolls everything back and names the file, line and column;
- refuses a clinic slug or a login email that already exists (no partial updates);
- in staging and production it asks for the clinic slug to be typed (or ``--confirm <slug>``);
- ``--dry-run`` checks everything and writes nothing;
- passwords are generated (or ``--password`` for all), hashed, and printed once at the end;
- nothing read from the files is logged; problems go to the terminal only.

The importing tool never sees the data: the developer runs it on the server.
"""

from __future__ import annotations

import argparse
import csv
import io
import secrets
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import partial
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Protocol, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from mediease_api.application.billing.fees import add_default_services
from mediease_api.application.reminders.appointment import schedule_appointment_reminders
from mediease_api.application.reminders.scheduling import sync_prescription_reminder
from mediease_api.application.scheduling.generation import generate
from mediease_api.bootstrap import SeedDependencies, build_seed_dependencies
from mediease_api.config.settings import load_settings
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.queue import transition
from mediease_api.domain.appointments.status import AppointmentSource, AppointmentStatus
from mediease_api.domain.billing.bill import (
    NO_DISCOUNT,
    Bill,
    BillKind,
    Discount,
    DiscountKind,
    LineInput,
    Numbering,
    financial_year,
    format_number,
    price_lines,
)
from mediease_api.domain.billing.fees import ServiceKind
from mediease_api.domain.billing.payment import Payment, PaymentKind, PaymentMode
from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.verification import VerificationSource
from mediease_api.domain.identity.membership import ClinicMembership, Role
from mediease_api.domain.identity.password import validate_password
from mediease_api.domain.identity.user import User
from mediease_api.domain.patients.patient import Language, Patient, Sex
from mediease_api.domain.portal.account import PatientAccount
from mediease_api.domain.portal.link import LinkMethod, PatientAccountLink
from mediease_api.domain.prescriptions.prescription import Advice, Prescription, PrescriptionItem
from mediease_api.domain.prescriptions.schedule import DurationKind, Frequency
from mediease_api.domain.prescriptions.vocabulary import Timing
from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import DomainError
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.time import local_date
from mediease_api.domain.subscriptions.subscription import Subscription
from mediease_api.domain.visits.visit import Visit
from mediease_api.domain.visits.vitals import Vitals
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

DEMO_PACKAGE = "mediease_api.delivery.cli"
DEMO_DIRECTORY = "demo_clinic"
OPS = "OPS"  # a staff.csv role: the platform ops user who verifies the clinic, in no clinic
TIMEZONE = "Asia/Kolkata"
WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")

T = TypeVar("T")


class ImportProblem(Exception):
    """A file, line and column, and what is wrong there. Never the value itself."""


class _Refused(Exception):
    """A problem found while writing; the step that raised it adds the row's location."""


# --- Reading the files ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileSpec:
    name: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()
    must_exist: bool = True


FILES: dict[str, FileSpec] = {
    spec.name: spec
    for spec in (
        FileSpec(
            "clinic.csv",
            ("name", "slug"),
            (
                "phone",
                "address_line",
                "city",
                "state",
                "pincode",
                "specialties",
                "booking_mode",
                "consultation_fee_rupees",
                "follow_up_fee_rupees",
            ),
        ),
        FileSpec(
            "staff.csv",
            ("email", "full_name", "role"),
            (
                "phone",
                "practises",
                "qualification",
                "registration_number",
                "registration_council",
                "specialty",
                "languages",
            ),
        ),
        FileSpec(
            "schedules.csv",
            ("doctor_email", "weekday", "start", "end"),
            ("slot_minutes", "capacity"),
        ),
        FileSpec(
            "patients.csv",
            ("ref", "full_name", "phone", "sex"),
            (
                "date_of_birth",
                "age_years",
                "guardian_name",
                "language",
                "whatsapp_consent",
                "sms_consent",
            ),
        ),
        FileSpec(
            "visits.csv",
            ("ref", "patient_ref", "doctor_email", "date", "time"),
            (
                "chief_complaint",
                "findings",
                "diagnosis",
                "notes",
                "bp_systolic",
                "bp_diastolic",
                "pulse",
                "spo2",
                "resp_rate",
                "temp_c",
                "weight_kg",
                "height_cm",
                "follow_up_date",
                "advice_diet",
                "advice_activity",
                "advice_return_if",
                "advice_notes",
            ),
            must_exist=False,
        ),
        FileSpec(
            "prescription_items.csv",
            ("visit_ref", "medicine_name"),
            (
                "form",
                "strength",
                "dose",
                "frequency",
                "frequency_text",
                "timing",
                "duration_days",
                "duration_kind",
                "quantity",
                "notes",
            ),
            must_exist=False,
        ),
        FileSpec(
            "bill_lines.csv",
            ("visit_ref", "description", "amount_rupees"),
            ("service", "quantity", "discount_rupees"),
            must_exist=False,
        ),
        FileSpec(
            "payments.csv",
            ("visit_ref", "mode"),
            ("amount_rupees", "reference"),
            must_exist=False,
        ),
        FileSpec(
            "appointments.csv",
            ("patient_ref", "doctor_email", "date"),
            ("time", "reason"),
            must_exist=False,
        ),
        FileSpec(
            "portal_accounts.csv",
            ("email", "patient_ref"),
            (),
            must_exist=False,
        ),
    )
}


@dataclass(frozen=True)
class Row:
    file: str
    line: int
    values: dict[str, str]

    def where(self, column: str | None = None) -> str:
        return f"{self.file} line {self.line}" + (f", column {column}" if column else "")

    def text(self, column: str) -> str | None:
        value = (self.values.get(column) or "").strip()
        return value or None

    def need(self, column: str) -> str:
        value = self.text(column)
        if value is None:
            raise ImportProblem(f"{self.where(column)}: is required")
        return value

    def parse(self, column: str, parser: Callable[[str], T]) -> T | None:
        """``parser`` applied to the column's text; its ValueError or domain error is located."""
        raw = self.text(column)
        if raw is None:
            return None
        try:
            return parser(raw)
        except ValueError as error:
            # Our parsers' own messages, which never contain the value.
            raise ImportProblem(f"{self.where(column)}: {error}") from None
        except DomainError as error:
            raise ImportProblem(f"{self.where(column)}: {error.message}") from None

    def parse_need(self, column: str, parser: Callable[[str], T]) -> T:
        self.need(column)
        value = self.parse(column, parser)
        assert value is not None
        return value


class _HasRow(Protocol):
    @property
    def row(self) -> Row: ...


# A folder on disk, or the bundled demo inside the package (both are Traversable).
Source = Traversable


def read_rows(source: Source, spec: FileSpec) -> list[Row]:
    path = source / spec.name
    if not path.is_file():
        if spec.must_exist:
            raise ImportProblem(f"{spec.name}: the file is missing")
        return []
    # utf-8-sig: Excel's "CSV UTF-8" starts with a byte-order mark. The csv module wants the
    # newlines untranslated, which only a text wrapper over the bytes offers on a Traversable.
    with io.TextIOWrapper(path.open("rb"), encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            raise ImportProblem(f"{spec.name}: the file is empty (it needs a header row)")
        columns = [c.strip().lower() for c in header]
        known = set(spec.required) | set(spec.optional)
        unknown = [c for c in columns if c and c not in known]
        if unknown:
            raise ImportProblem(f"{spec.name}: unknown column '{unknown[0]}' (check the spelling)")
        missing = [c for c in spec.required if c not in columns]
        if missing:
            raise ImportProblem(f"{spec.name}: the column '{missing[0]}' is missing")
        rows = []
        for number, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue
            if cells[0].lstrip().startswith("#"):
                continue  # a comment line
            if len(cells) > len(columns):
                raise ImportProblem(f"{spec.name} line {number}: more cells than columns")
            values = {col: cell for col, cell in zip(columns, cells, strict=False) if col}
            rows.append(Row(spec.name, number, values))
    return rows


# --- Values ---------------------------------------------------------------------------------------


def parse_day(raw: str, today: date) -> date:
    """``2026-11-10``, ``today``, ``today-3`` or ``today+2`` (days from the import day)."""
    text = raw.strip().lower().replace(" ", "")
    if text.startswith("today"):
        rest = text[len("today") :]
        if not rest:
            return today
        if rest[0] not in "+-" or not rest[1:].isdigit():
            raise ValueError("write today, today-3 or today+2")
        days = int(rest[1:])
        return today + timedelta(days=days if rest[0] == "+" else -days)
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError("write a date as 2026-11-10, or today-3 / today+2") from None


def parse_clock(raw: str) -> time:
    try:
        hours, minutes = raw.strip().split(":")
        return time(int(hours), int(minutes))
    except ValueError:
        raise ValueError("write a time as 24-hour HH:MM, e.g. 09:30 or 17:45") from None


def parse_bool(raw: str) -> bool:
    text = raw.strip().lower()
    if text in ("yes", "y", "true", "1"):
        return True
    if text in ("no", "n", "false", "0"):
        return False
    raise ValueError("write yes or no")


def parse_iso_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise ValueError("write a date as 1990-05-17") from None


def parse_paise(raw: str) -> int:
    try:
        amount = Decimal(raw.strip().replace(",", "").removeprefix("₹"))
    except InvalidOperation:
        raise ValueError("write rupees as 500 or 499.50") from None
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
        raise ValueError("write rupees as 500 or 499.50")
    return int(amount * 100)


def parse_int(raw: str) -> int:
    try:
        return int(raw.strip())
    except ValueError:
        raise ValueError("must be a whole number") from None


def parse_decimal(raw: str) -> float:
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        raise ValueError("must be a number such as 37.5") from None
    if not value.is_finite():
        raise ValueError("must be a number such as 37.5")
    return float(value)


def parse_list(raw: str) -> tuple[str, ...]:
    """Several values in one cell, separated by semicolons."""
    return tuple(part.strip() for part in raw.split(";") if part.strip())


def parse_language(raw: str) -> Language:
    text = raw.strip().lower()
    if text not in {lang.value for lang in Language}:
        raise ValueError("must be en or hi")
    return Language(text)


def parse_enum[E: StrEnum](
    kind: type[E], aliases: dict[str, str] | None = None
) -> Callable[[str], E]:
    def parse(raw: str) -> E:
        text = raw.strip().upper().replace(" ", "_").replace("-", "_")
        text = (aliases or {}).get(text, text)
        if text not in {member.value for member in kind}:
            names = ", ".join(member.value for member in kind)
            raise ValueError(f"must be one of {names}")
        return kind(text)

    return parse


def parse_weekday(raw: str) -> int:
    text = raw.strip().upper()[:3]
    if text not in WEEKDAYS:
        raise ValueError("write MON, TUE, WED, THU, FRI, SAT or SUN")
    return WEEKDAYS.index(text)


# --- The parsed data -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ClinicSpec:
    row: Row
    name: str
    slug: str
    phone: PhoneNumber | None
    address_line: str | None
    city: str | None
    state: str | None
    pincode: str | None
    specialties: tuple[str, ...]
    booking_mode: BookingMode
    consultation_paise: int | None
    follow_up_paise: int | None


@dataclass(frozen=True)
class StaffSpec:
    row: Row
    email: EmailAddress
    full_name: str
    role: Role | None  # None: the platform ops user
    phone: PhoneNumber | None
    practises: bool
    qualification: str | None
    registration_number: str | None
    registration_council: str | None
    specialty: str | None
    languages: tuple[str, ...]


@dataclass(frozen=True)
class BlockSpec:
    row: Row
    doctor_email: EmailAddress
    weekday: int
    shape: BlockShape


@dataclass(frozen=True)
class PatientSpec:
    row: Row
    ref: str
    full_name: str
    phone: PhoneNumber
    sex: Sex
    date_of_birth: date | None
    age_years: int | None
    guardian_name: str | None
    language: Language
    whatsapp: bool
    sms: bool


@dataclass(frozen=True)
class ItemSpec:
    row: Row
    medicine_name: str
    form: str | None
    strength: str | None
    dose: str | None
    frequency: Frequency | None
    frequency_text: str | None
    timing: Timing | None
    duration_days: int | None
    duration_kind: DurationKind | None
    quantity: str | None
    notes: str | None


@dataclass(frozen=True)
class LineSpec:
    row: Row
    description: str
    amount_paise: int
    service: ServiceKind | None
    quantity: int
    discount_paise: int


@dataclass(frozen=True)
class PaymentSpec:
    row: Row
    mode: PaymentMode
    amount_paise: int | None  # None: the bill's whole balance
    reference: str | None


@dataclass
class VisitSpec:
    row: Row
    ref: str
    patient_ref: str
    doctor_email: EmailAddress
    day: date
    at: datetime  # UTC
    text: dict[str, str | None]
    vitals: Vitals
    follow_up_date: date | None
    advice: Advice
    items: list[ItemSpec] = field(default_factory=list)
    lines: list[LineSpec] = field(default_factory=list)
    payments: list[PaymentSpec] = field(default_factory=list)


@dataclass(frozen=True)
class AppointmentSpec:
    row: Row
    patient_ref: str
    doctor_email: EmailAddress
    day: date
    at: datetime | None  # UTC; None: the day's first session (token mode)
    reason: str | None


@dataclass(frozen=True)
class AccountSpec:
    row: Row
    email: EmailAddress
    patient_ref: str


@dataclass
class Data:
    clinic: ClinicSpec
    staff: list[StaffSpec]
    blocks: list[BlockSpec]
    patients: list[PatientSpec]
    visits: list[VisitSpec]
    appointments: list[AppointmentSpec]
    accounts: list[AccountSpec]


def _email(raw: str) -> EmailAddress:
    return EmailAddress.parse(raw)


def _phone(raw: str) -> PhoneNumber:
    return PhoneNumber.parse(raw)


def _at(day: date, clock: time, tz: str) -> datetime:
    return datetime.combine(day, clock, tzinfo=ZoneInfo(tz)).astimezone(UTC)


def load(source: Source, *, now: datetime) -> Data:
    """Every file parsed and cross-checked; nothing is written. Raises ``ImportProblem``."""
    tz = TIMEZONE
    today = local_date(now, tz)

    def rows(name: str) -> list[Row]:
        return read_rows(source, FILES[name])

    clinic_rows = rows("clinic.csv")
    if len(clinic_rows) != 1:
        raise ImportProblem("clinic.csv: needs exactly one clinic row")
    clinic = _clinic(clinic_rows[0])

    staff = [_staff(r) for r in rows("staff.csv")]
    _unique(staff, lambda s: s.email.value, "email")
    by_email = {s.email.value: s for s in staff}
    if not any(s.role is Role.OWNER for s in staff):
        raise ImportProblem("staff.csv: needs at least one OWNER")
    practising = {s.email.value for s in staff if s.practises}

    def doctor_of(row: Row, column: str) -> EmailAddress:
        email = row.parse_need(column, _email)
        if email.value not in practising:
            raise ImportProblem(f"{row.where(column)}: is not a doctor in staff.csv")
        return email

    blocks = []
    for r in rows("schedules.csv"):
        shape = BlockShape(
            r.parse_need("start", parse_clock),
            r.parse_need("end", parse_clock),
            slot_minutes=r.parse("slot_minutes", parse_int),
            capacity=r.parse("capacity", parse_int),
        )
        try:
            shape.validate(clinic.booking_mode)
        except DomainError as error:
            raise ImportProblem(f"{r.where()}: {error.message}") from None
        blocks.append(
            BlockSpec(
                r, doctor_of(r, "doctor_email"), r.parse_need("weekday", parse_weekday), shape
            )
        )

    patients = [_patient(r) for r in rows("patients.csv")]
    _unique(patients, lambda p: p.ref, "ref")
    patient_refs = {p.ref for p in patients}

    def patient_of(row: Row) -> str:
        ref = row.need("patient_ref")
        if ref not in patient_refs:
            raise ImportProblem(f"{row.where('patient_ref')}: no patient with this ref")
        return ref

    visits: list[VisitSpec] = []
    for r in rows("visits.csv"):
        day = r.parse_need("date", lambda raw: parse_day(raw, today))
        at = _at(day, r.parse_need("time", parse_clock), tz)
        if at >= now:
            raise ImportProblem(
                f"{r.where('date')}: a visit must be in the past (use appointments.csv)"
            )
        follow_up = r.parse("follow_up_date", lambda raw: parse_day(raw, today))
        if follow_up is not None and follow_up <= day:
            raise ImportProblem(f"{r.where('follow_up_date')}: must be after the visit's date")
        visits.append(
            VisitSpec(
                row=r,
                ref=r.need("ref"),
                patient_ref=patient_of(r),
                doctor_email=doctor_of(r, "doctor_email"),
                day=day,
                at=at,
                text={k: r.text(k) for k in ("chief_complaint", "findings", "diagnosis", "notes")},
                vitals=_vitals(r),
                follow_up_date=follow_up,
                advice=_advice(r),
            )
        )
    _unique(visits, lambda v: v.ref, "ref")
    by_ref = {v.ref: v for v in visits}

    def visit_of(row: Row) -> VisitSpec:
        ref = row.need("visit_ref")
        if ref not in by_ref:
            raise ImportProblem(f"{row.where('visit_ref')}: no visit with this ref in visits.csv")
        return by_ref[ref]

    for r in rows("prescription_items.csv"):
        visit_of(r).items.append(_item(r))
    for r in rows("bill_lines.csv"):
        visit_of(r).lines.append(_line(r))
    for r in rows("payments.csv"):
        visit = visit_of(r)
        if not visit.lines:
            raise ImportProblem(f"{r.where('visit_ref')}: the visit has no bill lines to pay")
        visit.payments.append(
            PaymentSpec(
                r,
                r.parse_need("mode", parse_enum(PaymentMode)),
                r.parse("amount_rupees", parse_paise),
                r.text("reference"),
            )
        )

    appointments = []
    for r in rows("appointments.csv"):
        day = r.parse_need("date", lambda raw: parse_day(raw, today))
        if day < today:
            raise ImportProblem(f"{r.where('date')}: must be today or later (past ones are visits)")
        clock = r.parse("time", parse_clock)
        appointments.append(
            AppointmentSpec(
                r,
                patient_of(r),
                doctor_of(r, "doctor_email"),
                day,
                _at(day, clock, tz) if clock else None,
                r.text("reason"),
            )
        )

    accounts = []
    for r in rows("portal_accounts.csv"):
        email = r.parse_need("email", _email)
        if email.value in by_email:
            raise ImportProblem(f"{r.where('email')}: is already a staff login in staff.csv")
        accounts.append(AccountSpec(r, email, patient_of(r)))
    _unique(accounts, lambda a: a.email.value, "email")
    _unique(accounts, lambda a: a.patient_ref, "patient_ref")

    return Data(clinic, staff, blocks, patients, visits, appointments, accounts)


def _unique[H: _HasRow](items: Sequence[H], key: Callable[[H], str], column: str) -> None:
    seen: set[str] = set()
    for item in items:
        value = key(item)
        if value in seen:
            raise ImportProblem(f"{item.row.where(column)}: appears twice")
        seen.add(value)


def _clinic(r: Row) -> ClinicSpec:
    return ClinicSpec(
        row=r,
        name=r.need("name"),
        slug=r.need("slug").lower(),
        phone=r.parse("phone", _phone),
        address_line=r.text("address_line"),
        city=r.text("city"),
        state=r.text("state"),
        pincode=r.text("pincode"),
        specialties=r.parse("specialties", parse_list) or (),
        booking_mode=r.parse("booking_mode", parse_enum(BookingMode)) or BookingMode.TOKENS,
        consultation_paise=r.parse("consultation_fee_rupees", parse_paise),
        follow_up_paise=r.parse("follow_up_fee_rupees", parse_paise),
    )


def _staff(r: Row) -> StaffSpec:
    role_text = r.need("role").strip().upper().replace(" ", "_")
    role: Role | None
    if role_text == OPS:
        role = None
    else:
        role = r.parse_need("role", parse_enum(Role, {"DESK": "FRONT_DESK"}))
    practises = role is Role.DOCTOR or (
        role is Role.OWNER and bool(r.parse("practises", parse_bool))
    )
    spec = StaffSpec(
        row=r,
        email=r.parse_need("email", _email),
        full_name=r.need("full_name"),
        role=role,
        phone=r.parse("phone", _phone),
        practises=practises,
        qualification=r.text("qualification"),
        registration_number=r.text("registration_number"),
        registration_council=r.text("registration_council"),
        specialty=r.text("specialty"),
        languages=r.parse("languages", parse_list) or (),
    )
    if practises:
        for column in ("qualification", "registration_number", "registration_council"):
            r.need(column)  # printed on every prescription
    return spec


def _patient(r: Row) -> PatientSpec:
    return PatientSpec(
        row=r,
        ref=r.need("ref"),
        full_name=r.need("full_name"),
        phone=r.parse_need("phone", _phone),
        sex=r.parse_need("sex", parse_enum(Sex, {"F": "FEMALE", "M": "MALE", "O": "OTHER"})),
        date_of_birth=r.parse("date_of_birth", parse_iso_date),
        age_years=r.parse("age_years", parse_int),
        guardian_name=r.text("guardian_name"),
        language=r.parse("language", parse_language) or Language.EN,
        whatsapp=bool(r.parse("whatsapp_consent", parse_bool)),
        sms=bool(r.parse("sms_consent", parse_bool)),
    )


_VITALS_INT = ("bp_systolic", "bp_diastolic", "pulse", "spo2", "resp_rate")
_VITALS_DEC = ("temp_c", "weight_kg", "height_cm")


def _vitals(r: Row) -> Vitals:
    values: dict[str, object] = {k: r.parse(k, parse_int) for k in _VITALS_INT}
    values.update({k: r.parse(k, parse_decimal) for k in _VITALS_DEC})
    try:
        return Vitals.parse(values)
    except DomainError as error:
        raise ImportProblem(f"{r.where()}: vitals: {error.message}") from None


def _advice(r: Row) -> Advice:
    try:
        return Advice.create(
            diet=r.parse("advice_diet", parse_list) or (),
            activity=r.parse("advice_activity", parse_list) or (),
            return_if=r.parse("advice_return_if", parse_list) or (),
            notes=r.text("advice_notes"),
        )
    except DomainError as error:
        raise ImportProblem(f"{r.where()}: {error.message}") from None


def _item(r: Row) -> ItemSpec:
    return ItemSpec(
        row=r,
        medicine_name=r.need("medicine_name"),
        form=r.text("form"),
        strength=r.text("strength"),
        dose=r.text("dose"),
        frequency=r.parse("frequency", Frequency.parse),
        frequency_text=r.text("frequency_text"),
        timing=r.parse("timing", parse_enum(Timing)),
        duration_days=r.parse("duration_days", parse_int),
        duration_kind=r.parse("duration_kind", parse_enum(DurationKind)),
        quantity=r.text("quantity"),
        notes=r.text("notes"),
    )


def _line(r: Row) -> LineSpec:
    return LineSpec(
        row=r,
        description=r.need("description"),
        amount_paise=r.parse_need("amount_rupees", parse_paise),
        service=r.parse("service", parse_enum(ServiceKind, {"FOLLOWUP": "FOLLOW_UP"})),
        quantity=r.parse("quantity", parse_int) or 1,
        discount_paise=r.parse("discount_rupees", parse_paise) or 0,
    )


# --- Writing ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Login:
    email: str
    kind: str  # OWNER, DOCTOR, FRONT_DESK, OPS, PATIENT
    password: str


@dataclass
class Report:
    slug: str
    logins: list[Login] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    notes: list[str] = field(default_factory=list)


Passwords = Callable[[], str]


def generated_password() -> str:
    """16 URL-safe characters (~96 bits); the policy's floor is 12 characters of anything."""
    return secrets.token_urlsafe(12)


def write(deps: SeedDependencies, data: Data, *, passwords: Passwords, commit: bool) -> Report:
    """Build the clinic in one transaction. Raises ``ImportProblem`` (and rolls back)."""
    now = deps.clock.now()
    report = Report(data.clinic.slug)
    with deps.uow as uow:
        writer = _Writer(deps, uow, data, passwords, report, now)
        writer.run()
        if commit:
            uow.commit()
    return report


class _Writer:
    clinic: Clinic
    staff: TenantRepositories
    owner: User
    desk: User
    ops: User | None
    services: dict[ServiceKind, UUID]

    def __init__(
        self,
        deps: SeedDependencies,
        uow: UnitOfWork,
        data: Data,
        passwords: Passwords,
        report: Report,
        now: datetime,
    ) -> None:
        self.deps = deps
        self.uow = uow
        self.data = data
        self.passwords = passwords
        self.report = report
        self.now = now
        self.ids = deps.ids
        self.today = local_date(now, TIMEZONE)
        self.users: dict[str, User] = {}
        self.doctors: dict[str, Doctor] = {}
        self.patients: dict[str, Patient] = {}
        self.active: dict[UUID, list[Appointment]] = defaultdict(list)
        self.upcoming: list[tuple[Appointment, Session, Patient]] = []

    def run(self) -> None:
        self._refuse_existing()
        self._users()
        self._clinic()
        self._schedules()
        self._patients()
        # In time order, so tokens, bill numbers and the history read as they happened.
        for visit in sorted(self.data.visits, key=lambda v: v.at):
            self._located(visit.row, partial(self._visit, visit))
        for upcoming in self.data.appointments:
            self._located(upcoming.row, partial(self._upcoming, upcoming))
        for account in self.data.accounts:
            self._located(account.row, partial(self._account, account))
        # After the app logins exist: an app user's appointment is reminded in the app.
        for booked, session, patient in self.upcoming:
            self._remind(booked, session, patient)
        self.uow.clinics.update(self.clinic)

    @staticmethod
    def _located(row: Row, step: Callable[[], None]) -> None:
        """Each step names the row it works on, so a domain refusal points at the data."""
        try:
            step()
        except DomainError as error:
            raise ImportProblem(f"{row.where()}: {error.message}") from None
        except _Refused as refused:
            raise ImportProblem(f"{row.where()}: {refused}") from None

    def _refuse_existing(self) -> None:
        spec = self.data.clinic
        if self.uow.clinics.get_by_slug(spec.slug) is not None:
            raise ImportProblem(f"{spec.row.where('slug')}: a clinic with this slug already exists")
        for person in self.data.staff:
            if person.role is None:
                continue  # an existing ops user is reused as the verifier
            if self.uow.users.get_by_email(person.email) is not None:
                raise ImportProblem(f"{person.row.where('email')}: this login already exists")
        for account in self.data.accounts:
            if self.uow.patient_accounts.get_password_account(account.email) is not None:
                raise ImportProblem(f"{account.row.where('email')}: this login already exists")

    def _login(self, email: EmailAddress, kind: str) -> str:
        password = self.passwords()
        validate_password(password)
        self.report.logins.append(Login(email.value, kind, password))
        return self.deps.hasher.hash(password)

    def _users(self) -> None:
        for person in self.data.staff:
            existing = self.uow.users.get_by_email(person.email) if person.role is None else None
            if existing is not None:
                self.users[person.email.value] = existing
                continue

            def make(p: StaffSpec = person) -> None:
                user = User.create(
                    id=self.ids.new_id(),
                    full_name=p.full_name,
                    email=p.email,
                    phone=p.phone,
                    is_platform_ops=p.role is None,
                    password_hash=self._login(p.email, p.role.value if p.role else OPS),
                    now=self.now,
                )
                self.uow.users.add(user)
                self.users[p.email.value] = user

            self._located(person.row, make)
        self.owner = next(
            self.users[s.email.value] for s in self.data.staff if s.role is Role.OWNER
        )
        desk = next((s for s in self.data.staff if s.role is Role.FRONT_DESK), None)
        self.desk = self.users[desk.email.value] if desk else self.owner
        ops = next((s for s in self.data.staff if s.role is None), None)
        self.ops = self.users[ops.email.value] if ops else None

    def _clinic(self) -> None:
        spec = self.data.clinic
        now = self.now

        def make() -> None:
            self.clinic = Clinic.create(
                id=self.ids.new_id(),
                name=spec.name,
                slug=spec.slug,
                now=now,
                timezone=TIMEZONE,
                phone=spec.phone,
                address_line=spec.address_line,
                city=spec.city,
                state=spec.state,
                pincode=spec.pincode,
                specialties=spec.specialties,
                booking_mode=spec.booking_mode,
            )

        self._located(spec.row, make)
        self.uow.clinics.add(self.clinic)
        self.staff: TenantRepositories = self.uow.tenant(self.clinic.id)
        add_default_services(self.staff, self.clinic.id, self.ids, now)
        prices = {
            ServiceKind.CONSULTATION: spec.consultation_paise,
            ServiceKind.FOLLOW_UP: spec.follow_up_paise,
        }
        self.services: dict[ServiceKind, UUID] = {}
        for service in self.staff.fees.list_services():
            self.services.setdefault(service.kind, service.id)
            price = prices.get(service.kind)
            if price is not None:
                service.change(now=now, default_price_paise=price)
                self.staff.fees.update_service(service)
        # A demo or partner clinic keeps working until the deliverable ends: no trial countdown.
        self.uow.subscriptions.add(Subscription.legacy(self.clinic.id, now))

        for person in self.data.staff:
            if person.role is None:
                continue
            user = self.users[person.email.value]

            def member(p: StaffSpec = person, u: User = user) -> None:
                assert p.role is not None
                membership = ClinicMembership.invite(
                    id=self.ids.new_id(),
                    clinic_id=self.clinic.id,
                    user_id=u.id,
                    role=p.role,
                    now=now,
                )
                membership.activate(now=now)
                self.staff.memberships.add(membership)
                if p.practises:
                    doctor = Doctor.create(
                        id=self.ids.new_id(),
                        clinic_id=self.clinic.id,
                        user_id=u.id,
                        display_name=p.full_name,
                        qualification=p.qualification or "",
                        registration_number=p.registration_number or "",
                        registration_council=p.registration_council or "",
                        specialty=p.specialty,
                        now=now,
                    )
                    if p.languages:
                        doctor.set_profile(languages=p.languages, show_fee=True, now=now)
                    if self.ops is not None:
                        doctor.verify(by=self.ops.id, source=VerificationSource.OPS_CHECK, now=now)
                        doctor.set_visible(True, now=now)
                    self.staff.doctors.add(doctor)
                    self.doctors[p.email.value] = doctor

            self._located(person.row, member)

        self.clinic.activate(
            active_owner_count=self.staff.memberships.count_active_owners(), now=now
        )
        if self.ops is not None:
            self.clinic.verify(by=self.ops.id, source=VerificationSource.OPS_CHECK, now=now)
            self.clinic.set_listed(True, now=now)
        else:
            self.report.notes.append(
                "No OPS row in staff.csv: the clinic is not verified, so its public page and "
                "online booking stay off until ops verifies it."
            )

    def _schedules(self) -> None:
        # Valid from the earliest visit, so each past visit falls in a session of its day.
        first = min([v.day for v in self.data.visits] + [self.today])
        for block in self.data.blocks:
            doctor = self.doctors[block.doctor_email.value]

            def make(b: BlockSpec = block, d: Doctor = doctor) -> None:
                self.staff.schedules.add(
                    WeeklyBlock.create(
                        id=self.ids.new_id(),
                        clinic_id=self.clinic.id,
                        doctor_id=d.id,
                        weekday=b.weekday,
                        shape=b.shape,
                        mode=self.clinic.booking_mode,
                        valid_from=first,
                        now=self.now,
                    )
                )

            self._located(block.row, make)
        self.report.counts["schedule blocks"] = len(self.data.blocks)

    def _patients(self) -> None:
        first_seen: dict[str, datetime] = {}
        for visit in self.data.visits:
            known = first_seen.get(visit.patient_ref)
            if known is None or visit.at < known:
                first_seen[visit.patient_ref] = visit.at
        for spec in self.data.patients:
            # Registered on the day of their first visit (or now): the history reads in order.
            at = first_seen.get(spec.ref, self.now) - timedelta(hours=1)

            def make(p: PatientSpec = spec, at: datetime = at) -> None:
                patient = Patient.create(
                    id=self.ids.new_id(),
                    clinic_id=self.clinic.id,
                    code=self.clinic.allocate_patient_code(now=at),
                    full_name=p.full_name,
                    phone=p.phone,
                    sex=p.sex,
                    registered_on=local_date(at, TIMEZONE),
                    created_by=self.desk.id,
                    now=at,
                    date_of_birth=p.date_of_birth,
                    age_years=p.age_years,
                    guardian_name=p.guardian_name,
                    language=p.language,
                )
                if p.whatsapp or p.sms:
                    patient.record_consent(whatsapp=p.whatsapp, sms=p.sms, by=self.desk.id, now=at)
                self.staff.patients.add(patient)
                self.patients[p.ref] = patient

            self._located(spec.row, make)
        self.report.counts["patients"] = len(self.data.patients)

    # --- Sessions and bookings -------------------------------------------------------------

    def _session_at(
        self, doctor: Doctor, day: date, at: datetime | None, *, generated_at: datetime
    ) -> Session:
        generate(
            self.staff,
            clinic=self.clinic,
            doctor=doctor,
            on_date=day,
            ids=self.ids,
            now=generated_at,
        )
        sessions = sorted(
            self.staff.sessions.list_for_date(day, doctor_id=doctor.id), key=lambda s: s.starts_at
        )
        for session in sessions:
            if at is None and session.ends_at > self.now:
                return session
            if at is not None and session.starts_at <= at < session.ends_at:
                return session
        local = "the day" if at is None else at.astimezone(ZoneInfo(TIMEZONE)).strftime("%H:%M")
        raise _Refused(
            f"no session of {doctor.display_name} covers {local} on {day.isoformat()}"
            " (check schedules.csv for that weekday)"
        )

    def _slot(self, session: Session, at: datetime | None) -> datetime | None:
        if session.mode is not BookingMode.SLOTS:
            return None
        if at is None:
            raise _Refused("slot booking needs a time")
        for start, end in session.slots():
            if start <= at < end:
                return start
        raise _Refused("the time is not on the session's slot grid")

    def _book(
        self,
        session: Session,
        patient: Patient,
        at: datetime | None,
        *,
        now: datetime,
        reason: str | None,
    ) -> Appointment:
        appointment = Appointment.book(
            session,
            id=self.ids.new_id(),
            patient_id=patient.id,
            active=self.active[session.id],
            now=now,
            slot_start=self._slot(session, at),
            source=AppointmentSource.FRONT_DESK,
            reason=reason,
            created_by=self.desk.id,
        )
        self.active[session.id].append(appointment)
        return appointment

    # --- A past visit ------------------------------------------------------------------------

    def _visit(self, spec: VisitSpec) -> None:
        doctor = self.doctors[spec.doctor_email.value]
        patient = self.patients[spec.patient_ref]
        assert doctor.user_id is not None
        at = spec.at
        session = self._session_at(doctor, spec.day, at, generated_at=at - timedelta(days=1))
        appointment = self._book(session, patient, at, now=at - timedelta(minutes=30), reason=None)
        for step, to in enumerate(
            (AppointmentStatus.ARRIVED, AppointmentStatus.IN_CONSULTATION), start=1
        ):
            transition(
                appointment,
                session,
                seen=appointment.status,
                to=to,
                now=at - timedelta(minutes=10 * (2 - step)),
                today=spec.day,
            )
        visit = Visit.start(
            appointment,
            id=self.ids.new_id(),
            doctor_id=doctor.id,
            created_by=doctor.user_id,
            now=at,
        )
        changes: dict[str, object] = {k: v for k, v in spec.text.items() if v is not None}
        if spec.vitals != Vitals.empty():
            changes["vitals"] = spec.vitals
        if changes:
            visit.edit(changes, seen_revision=visit.revision, now=at + timedelta(minutes=5))
        done = at + timedelta(minutes=12)
        transition(
            appointment,
            session,
            seen=appointment.status,
            to=AppointmentStatus.COMPLETED,
            now=done,
            today=spec.day,
        )
        self.staff.sessions.update(session)
        self.staff.appointments.add(appointment)
        self.staff.visits.add(visit)
        rx = self._prescription(spec, visit, doctor, patient, at + timedelta(minutes=10))
        visit.complete(done)
        self.staff.visits.update(visit)
        self._bill(spec, visit, doctor, patient, done + timedelta(minutes=3))
        self.report.counts["past visits"] += 1
        if rx is not None and rx.follow_up_date is not None and rx.follow_up_date > self.today:
            # A follow-up still ahead is reminded about, as if the prescription were issued now.
            sync_prescription_reminder(
                self.uow,
                self.staff,
                ids=self.ids,
                rx=rx,
                chain_id=rx.id,
                timezone=TIMEZONE,
                user_id=doctor.user_id,
                request_id=None,
                now=self.now,
            )
            self.report.counts["follow-up reminders"] += 1

    def _prescription(
        self, spec: VisitSpec, visit: Visit, doctor: Doctor, patient: Patient, at: datetime
    ) -> Prescription | None:
        if not spec.items and spec.advice.is_empty and spec.follow_up_date is None:
            return None
        assert doctor.user_id is not None
        items = []
        for position, item in enumerate(spec.items, start=1):
            try:
                items.append(
                    PrescriptionItem.create(
                        id=self.ids.new_id(),
                        position=position,
                        medicine_name=item.medicine_name,
                        form=item.form,
                        strength=item.strength,
                        dose=item.dose,
                        frequency=item.frequency,
                        frequency_text=item.frequency_text,
                        timing=item.timing,
                        duration_days=item.duration_days,
                        duration_kind=item.duration_kind,
                        quantity=item.quantity,
                        notes=item.notes,
                    )
                )
            except DomainError as error:
                raise ImportProblem(f"{item.row.where()}: {error.message}") from None
        rx = Prescription.first_draft(
            visit, id=self.ids.new_id(), created_by=doctor.user_id, now=at
        )
        rx.replace_body(
            items=items,
            advice=spec.advice,
            follow_up_date=spec.follow_up_date,
            seen_revision=rx.revision,
            today=spec.day,
            now=at,
        )
        self.staff.prescriptions.add(rx)
        # History: the link was not messaged then, so nothing is sent for it now.
        rx.issue(
            doctor=doctor,
            clinic=self.clinic,
            language=patient.language,
            may_message=False,
            seen_revision=rx.revision,
            today=spec.day,
            now=at,
        )
        self.staff.prescriptions.update(rx)
        self.report.counts["prescriptions"] += 1
        return rx

    def _bill(
        self, spec: VisitSpec, visit: Visit, doctor: Doctor, patient: Patient, at: datetime
    ) -> None:
        if not spec.lines:
            return
        inputs = []
        for line in spec.lines:
            unit = line.amount_paise
            discount = (
                Discount(DiscountKind.AMOUNT, line.discount_paise)
                if line.discount_paise
                else NO_DISCOUNT
            )
            inputs.append(
                LineInput(
                    description=line.description,
                    unit_price_paise=unit,
                    quantity=line.quantity,
                    discount=discount,
                    service_id=self.services.get(line.service) if line.service else None,
                )
            )
        try:
            priced = price_lines(inputs, NO_DISCOUNT, iter(self.ids.new_id, None))
        except DomainError as error:
            raise ImportProblem(f"{spec.lines[0].row.where()}: {error.message}") from None
        bill = Bill.draft(
            id=self.ids.new_id(),
            clinic_id=self.clinic.id,
            patient_id=patient.id,
            visit_id=visit.id,
            doctor_id=doctor.id,
            priced=priced,
            discount=NO_DISCOUNT,
            notes=None,
            by=self.desk.id,
            now=at,
        )
        self.staff.bills.add(bill)
        day = local_date(at, TIMEZONE)
        year = financial_year(day)
        seq = self.staff.bills.next_seq(BillKind.BILL, year)
        number = format_number(self.clinic.patient_code_prefix, BillKind.BILL, year, seq)
        bill.issue(Numbering(year, seq, number, day), by=self.desk.id, now=at)
        self.staff.bills.update(bill)
        self.report.counts["bills"] += 1
        for payment_spec in spec.payments:
            amount = payment_spec.amount_paise or bill.balance_paise
            if amount <= 0:
                continue
            try:
                payment = Payment.record(
                    bill,
                    id=self.ids.new_id(),
                    kind=PaymentKind.PAYMENT,
                    mode=payment_spec.mode,
                    amount_paise=amount,
                    reference=payment_spec.reference,
                    by=self.desk.id,
                    now=at,
                    today=day,
                )
            except DomainError as error:
                raise ImportProblem(f"{payment_spec.row.where()}: {error.message}") from None
            self.staff.payments.add(payment)
            self.staff.bills.update(bill)
            self.report.counts["payments"] += 1

    # --- Upcoming appointments and portal logins --------------------------------------------

    def _upcoming(self, spec: AppointmentSpec) -> None:
        doctor = self.doctors[spec.doctor_email.value]
        patient = self.patients[spec.patient_ref]
        session = self._session_at(doctor, spec.day, spec.at, generated_at=self.now)
        appointment = self._book(session, patient, spec.at, now=self.now, reason=spec.reason)
        self.staff.sessions.update(session)
        self.staff.appointments.add(appointment)
        self.upcoming.append((appointment, session, patient))
        self.report.counts["upcoming appointments"] += 1

    def _remind(self, appointment: Appointment, session: Session, patient: Patient) -> None:
        made = schedule_appointment_reminders(
            self.uow,
            self.staff,
            ids=self.ids,
            clinic=self.clinic,
            appointment=appointment,
            session=session,
            patient=patient,
            created_by=self.desk.id,
            request_id=None,
            now=self.now,
        )
        self.report.counts["appointment reminders"] += len(made)

    def _account(self, spec: AccountSpec) -> None:
        patient = self.patients[spec.patient_ref]
        account = PatientAccount.with_password(
            id=self.ids.new_id(),
            full_name=patient.full_name,
            email=spec.email,
            password_hash=self._login(spec.email, "PATIENT"),
            now=self.now,
            language=patient.language,
        )
        account.verify_email(now=self.now)
        self.uow.patient_accounts.add(account)
        self.staff.portal_links.add(
            PatientAccountLink.create(
                id=self.ids.new_id(),
                clinic_id=self.clinic.id,
                patient_id=patient.id,
                account_id=account.id,
                method=LinkMethod.INVITE,
                created_by_user_id=self.desk.id,
                now=self.now,
            )
        )
        self.report.counts["patient app logins"] += 1


# --- The command ---------------------------------------------------------------------------------


def demo_source() -> Traversable:
    return resources.files(DEMO_PACKAGE) / DEMO_DIRECTORY


def _confirmed(slug: str, env: str, confirm: str | None, ask: Callable[[str], str]) -> bool:
    if confirm is not None:
        return confirm == slug
    answer = ask(f"This writes clinic '{slug}' into the {env} database. Type its slug to go on: ")
    return answer.strip() == slug


def main(argv: Sequence[str] | None = None, *, ask: Callable[[str], str] = input) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--dir", type=Path, help="the folder with the CSV files")
    where.add_argument("--demo", action="store_true", help="the bundled demo clinic")
    parser.add_argument(
        "--password",
        help="one password for every login (at least 12 characters); generated when left out",
    )
    parser.add_argument("--dry-run", action="store_true", help="check everything, write nothing")
    parser.add_argument("--confirm", metavar="SLUG", help="the slug, instead of typing it")
    args = parser.parse_args(argv)

    settings = load_settings()
    deps = build_seed_dependencies(settings)
    source: Source = demo_source() if args.demo else args.dir
    if args.password is not None:
        try:
            validate_password(args.password)
        except DomainError as error:
            print(f"import: --password {error.message.split(': ', 1)[-1]}", file=sys.stderr)
            return 2
    try:
        data = load(source, now=deps.clock.now())
    except ImportProblem as problem:
        print(f"import: {problem}", file=sys.stderr)
        return 1
    if (
        settings.APP_ENV.is_deployed
        and not args.dry_run
        and not _confirmed(data.clinic.slug, settings.APP_ENV.value, args.confirm, ask)
    ):
        print("import: not confirmed; nothing written", file=sys.stderr)
        return 2
    fixed = args.password
    try:
        report = write(
            deps,
            data,
            passwords=(lambda: fixed) if fixed else generated_password,
            commit=not args.dry_run,
        )
    except ImportProblem as problem:
        print(f"import: {problem}; nothing written", file=sys.stderr)
        return 1
    _print(report, dry_run=args.dry_run, shown=fixed is None)
    return 0


def _print(report: Report, *, dry_run: bool, shown: bool) -> None:
    verb = "checked (dry run, nothing written)" if dry_run else "imported"
    print(f"import: clinic '{report.slug}' {verb}")
    for name, count in report.counts.items():
        print(f"import:   {count} {name}")
    for note in report.notes:
        print(f"import: note: {note}")
    if dry_run:
        return
    print("import: logins (shown once; keep them in a password manager):")
    width = max((len(login.email) for login in report.logins), default=0)
    for login in report.logins:
        secret = login.password if shown else "(the --password you gave)"
        print(f"  {login.email.ljust(width)}  {login.kind:<10}  {secret}")


if __name__ == "__main__":
    raise SystemExit(main())
