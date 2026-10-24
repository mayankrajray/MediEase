"""What a printed prescription says, resolved into lines (spec prescriptions R8, R18, R20; M4-P4).

``build_document`` turns an issued version, its patient and the clinic's paper size into an
``RxDocument``: every label and structured phrase already in the version's language
(``phrasebook``), every text the doctor wrote exactly as written. The renderer only lays it out,
so what the PDF says is decided and tested here, without a renderer.

What comes from where (M4-P4 concept 3): content, doctor, letterhead and language from the issued
version (frozen at issue); the patient's name, code, sex and age *on the issue date* when the PDF
is first rendered, after which the stored file never changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from mediease_api.domain.clinics.clinic import PaperSize
from mediease_api.domain.patients.patient import Language, Patient, Sex
from mediease_api.domain.prescriptions.errors import NotIssued
from mediease_api.domain.prescriptions.phrasebook import phrase
from mediease_api.domain.prescriptions.prescription import (
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
)
from mediease_api.domain.prescriptions.schedule import DAY_ORDER, DurationKind, Frequency, Slot
from mediease_api.domain.prescriptions.vocabulary import (
    PreparationCode,
    StorageCode,
)
from mediease_api.domain.shared.time import local_date

PRINTABLE = (PrescriptionStatus.ISSUED, PrescriptionStatus.SUPERSEDED)


@dataclass(frozen=True, slots=True)
class RxField:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class RxMedicine:
    number: int
    name: str
    form_strength: str | None
    details: tuple[RxField, ...]


@dataclass(frozen=True, slots=True)
class RxAdvice:
    heading: str
    entries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RxDocument:
    """One prescription version as printed. Every string is final text."""

    language: Language
    paper_size: PaperSize
    # The template to use (M4-P5): the one current when the version was issued.
    layout_version: int
    title: str
    revision_note: str | None
    clinic_name: str
    clinic_lines: tuple[str, ...]
    doctor_name: str
    doctor_lines: tuple[str, ...]
    patient: tuple[RxField, ...]
    issued_on: RxField
    medicines_heading: str
    medicines: tuple[RxMedicine, ...]
    advice_heading: str
    advice: tuple[RxAdvice, ...]
    advice_notes: RxField | None
    follow_up: RxField | None
    footer: str
    # "Page {page} of {pages}" split around the two numbers, for the print stylesheet.
    page_label: tuple[str, str, str]
    # Layout 2 (M6b-P3): the Medicine schedule section; layout 1 templates ignore it.
    schedule_heading: str = ""
    schedule_columns: tuple[str, ...] = ()
    schedule: tuple[RxScheduleRow, ...] = ()
    schedule_start: str | None = None
    schedule_medicine: str = ""
    schedule_as_written: str = ""


def pdf_object_key(clinic_id: UUID, prescription_id: UUID, version: int) -> str:
    """R18, ADR-0012: where a version's PDF is stored; one key per version, written once."""
    return f"rx/{clinic_id}/{prescription_id}/v{version}.pdf"


def format_date(day: date, language: Language) -> str:
    return f"{day.day} {phrase(f'month.{day.month}', language)} {day.year}"


def format_phone(e164: str) -> str:
    """An Indian number as people write it (+91 98765 43210); anything else unchanged."""
    if e164.startswith("+91") and len(e164) == 13:
        return f"+91 {e164[3:8]} {e164[8:]}"
    return e164


def _sentence(text: str, language: Language) -> str:
    return text[:1].upper() + text[1:] if language is Language.EN else text


def sentence(text: str, language: Language) -> str:
    """A phrase standing on its own: capitalised in English (Hindi has no case)."""
    return _sentence(text, language)


def _and_list(words: list[str], language: Language) -> str:
    if len(words) == 1:
        return words[0]
    return f"{', '.join(words[:-1])} {phrase('list.and', language)} {words[-1]}"


def frequency_words(frequency: Frequency, custom: str | None, language: Language) -> str:
    """M6b-P3: a pattern worded from its slots (`schedule.SLOT_SETS`), never per code; SOS and
    ONCE from the phrasebook; CUSTOM exactly as the doctor wrote it."""
    if frequency.is_custom:
        assert custom is not None
        return custom
    slots = frequency.slots
    if not slots:
        return phrase(f"frequency.{frequency.value}", language)
    times = phrase(f"frequency.times.{len(slots)}", language)
    if len(slots) == 1:
        return f"{times}, {phrase(f'slot.in.{slots[0].value}', language)}"
    return (
        f"{times}, {_and_list([phrase(f'slot.word.{s.value}', language) for s in slots], language)}"
    )


def when_text(item: PrescriptionItem, language: Language) -> str | None:
    parts: list[str] = []
    if item.frequency is not None:
        parts.append(frequency_words(item.frequency, item.frequency_text, language))
    if item.timing is not None:
        parts.append(phrase(f"timing.{item.timing.value}", language))
    return _sentence(", ".join(parts), language) if parts else None


def duration_text(days: int, language: Language) -> str:
    return (
        phrase("duration.day", language)
        if days == 1
        else phrase("duration.days", language, days=days)
    )


def duration_words(item: PrescriptionItem, language: Language) -> str:
    """Prescriptions R23: the doctor's duration in words; none stated is said so, never guessed."""
    if item.duration_kind is DurationKind.DAYS:
        assert item.duration_days is not None
        return duration_text(item.duration_days, language)
    if item.duration_kind is None:
        return phrase("duration.not_stated", language)
    return phrase(f"duration.{item.duration_kind.value}", language)


# Layout 2 (M6b-P3) adds the schedule section and says when a duration was not stated; a
# version issued on layout 1 keeps its words as issued (prescriptions R25).
SCHEDULE_LAYOUT = 2


def duration_field(item: PrescriptionItem, language: Language, layout: int) -> str | None:
    if layout < SCHEDULE_LAYOUT and item.duration_kind is None:
        return None
    return duration_words(item, language)


@dataclass(frozen=True, slots=True)
class RxScheduleRow:
    """One line of the Medicine schedule (R25): what the doctor wrote, laid out by time of day."""

    number: int
    name: str
    dose: str | None
    marks: tuple[bool, ...]  # one per `DAY_ORDER` slot: the doctor's pattern marks it
    # SOS, ONCE, CUSTOM: the words instead of marks; no frequency: "Times not stated".
    as_written: str | None
    timing: str | None
    how: str | None
    duration: str


def schedule_columns(language: Language) -> tuple[str, ...]:
    return tuple(phrase(f"slot.{s.value}", language) for s in DAY_ORDER)


def schedule_rows(rx: Prescription, language: Language) -> tuple[RxScheduleRow, ...]:
    """The schedule section of the PDF (layout 2) and the patient page, from the one engine."""
    rows = []
    for item in rx.items:
        slots: tuple[Slot, ...] = item.frequency.slots if item.frequency else ()
        as_written: str | None = None
        if not slots:
            as_written = (
                frequency_words(item.frequency, item.frequency_text, language)
                if item.frequency
                else phrase("schedule.not_stated", language)
            )
        rows.append(
            RxScheduleRow(
                number=item.position,
                name=item.medicine_name,
                dose=item.dose,
                marks=tuple(s in slots for s in DAY_ORDER),
                as_written=as_written,
                timing=phrase(f"timing.{item.timing.value}", language) if item.timing else None,
                how=preparation_text(item, language),
                duration=duration_words(item, language),
            )
        )
    return tuple(rows)


def preparation_text(item: PrescriptionItem, language: Language) -> str | None:
    lines = []
    for p in item.preparation:
        if p.code is PreparationCode.CUSTOM:
            assert p.text is not None
            lines.append(p.text)
        elif p.code is PreparationCode.DILUTE_IN_WATER:
            lines.append(phrase(f"preparation.{p.code.value}", language, amount=p.text))
        else:
            lines.append(phrase(f"preparation.{p.code.value}", language))
    return "; ".join(lines) or None


def storage_text(item: PrescriptionItem, language: Language) -> str | None:
    lines = []
    for s in item.storage:
        if s.code is StorageCode.DISCARD_AFTER_DAYS:
            lines.append(phrase(f"storage.{s.code.value}", language, days=s.days))
        else:
            lines.append(phrase(f"storage.{s.code.value}", language))
    return "; ".join(lines) or None


def _medicine(item: PrescriptionItem, language: Language, layout: int) -> RxMedicine:
    values = [
        ("item.dose", item.dose),
        ("item.when", when_text(item, language)),
        ("item.duration", duration_field(item, language, layout)),
        ("item.quantity", item.quantity),
        ("item.preparation", preparation_text(item, language)),
        ("item.storage", storage_text(item, language)),
        ("item.warnings", item.warnings),
        ("item.notes", item.notes),
    ]
    form_strength = " · ".join(v for v in (item.form, item.strength) if v) or None
    return RxMedicine(
        number=item.position,
        name=item.medicine_name,
        form_strength=form_strength,
        details=tuple(RxField(phrase(key, language), v) for key, v in values if v),
    )


def age_text(patient: Patient, on: date, language: Language) -> str:
    years = patient.age_years(on)
    return (
        phrase("age.infant", language) if years < 1 else phrase("age.years", language, years=years)
    )


def build_document(
    rx: Prescription, patient: Patient, *, paper_size: PaperSize, timezone: str
) -> RxDocument:
    """The printed form of an issued (or superseded) version; a draft is ``RX_NOT_ISSUED``."""
    if rx.status not in PRINTABLE:
        raise NotIssued(rx.status.value)
    assert rx.issued_at and rx.language and rx.doctor_snapshot and rx.clinic_snapshot
    assert patient.id == rx.patient_id, "the prescription's own patient"
    lang = rx.language
    issued_on = local_date(rx.issued_at, timezone)
    clinic, doctor = rx.clinic_snapshot, rx.doctor_snapshot

    place = ", ".join(v for v in (clinic.city, clinic.state) if v)
    if clinic.pincode:
        place = f"{place} {clinic.pincode}".strip()
    clinic_lines = tuple(v for v in (clinic.address_line, place) if v)
    if clinic.phone_e164:
        clinic_lines += (f"{phrase('phone', lang)}: {format_phone(clinic.phone_e164)}",)

    registration = phrase(
        "registration",
        lang,
        number=doctor.registration_number,
        council=doctor.registration_council,
    )
    doctor_lines = tuple(v for v in (doctor.qualification, doctor.specialty, registration) if v)

    people = [
        RxField(phrase("patient", lang), patient.full_name),
        RxField(phrase("patient_code", lang), patient.code),
        RxField(phrase("age", lang), age_text(patient, issued_on, lang)),
    ]
    if patient.sex is not Sex.UNDISCLOSED:
        people.append(RxField(phrase("sex", lang), phrase(f"sex.{patient.sex.value}", lang)))

    advice = tuple(
        RxAdvice(phrase(key, lang), entries)
        for key, entries in (
            ("advice.diet", rx.advice.diet),
            ("advice.activity", rx.advice.activity),
            ("advice.return_if", rx.advice.return_if),
        )
        if entries
    )
    page = phrase("page", lang, page="\0", pages="\0").split("\0")
    assert len(page) == 3, "the page label has both numbers"

    return RxDocument(
        language=lang,
        paper_size=paper_size,
        layout_version=rx.layout_version,
        title=phrase("title", lang),
        revision_note=phrase("revised", lang, version=rx.version) if rx.version > 1 else None,
        clinic_name=clinic.name,
        clinic_lines=clinic_lines,
        doctor_name=doctor.display_name,
        doctor_lines=doctor_lines,
        patient=tuple(people),
        issued_on=RxField(phrase("date", lang), format_date(issued_on, lang)),
        medicines_heading=phrase("medicines", lang),
        medicines=tuple(_medicine(item, lang, rx.layout_version) for item in rx.items),
        advice_heading=phrase("advice", lang),
        advice=advice,
        advice_notes=(
            RxField(phrase("advice.notes", lang), rx.advice.notes) if rx.advice.notes else None
        ),
        follow_up=(
            RxField(phrase("follow_up", lang), format_date(rx.follow_up_date, lang))
            if rx.follow_up_date
            else None
        ),
        footer=phrase("footer", lang),
        page_label=(page[0], page[1], page[2]),
        schedule_heading=phrase("schedule", lang),
        schedule_columns=schedule_columns(lang),
        schedule=schedule_rows(rx, lang) if rx.layout_version >= SCHEDULE_LAYOUT else (),
        schedule_start=phrase(
            "schedule.from", lang, date=format_date(rx.starts_on or issued_on, lang)
        ),
        schedule_medicine=phrase("schedule.medicine", lang),
        schedule_as_written=phrase("schedule.as_written", lang),
    )
