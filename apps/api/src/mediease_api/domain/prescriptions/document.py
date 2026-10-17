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
from mediease_api.domain.prescriptions.vocabulary import (
    Frequency,
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


def _when(item: PrescriptionItem, language: Language) -> str | None:
    parts: list[str] = []
    if item.frequency is Frequency.CUSTOM:
        assert item.frequency_text is not None
        parts.append(item.frequency_text)
    elif item.frequency is not None:
        parts.append(phrase(f"frequency.{item.frequency.value}", language))
    if item.timing is not None:
        parts.append(phrase(f"timing.{item.timing.value}", language))
    return _sentence(", ".join(parts), language) if parts else None


def _duration(days: int, language: Language) -> str:
    return (
        phrase("duration.day", language)
        if days == 1
        else phrase("duration.days", language, days=days)
    )


def _preparation(item: PrescriptionItem, language: Language) -> str | None:
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


def _storage(item: PrescriptionItem, language: Language) -> str | None:
    lines = []
    for s in item.storage:
        if s.code is StorageCode.DISCARD_AFTER_DAYS:
            lines.append(phrase(f"storage.{s.code.value}", language, days=s.days))
        else:
            lines.append(phrase(f"storage.{s.code.value}", language))
    return "; ".join(lines) or None


def _medicine(item: PrescriptionItem, language: Language) -> RxMedicine:
    values = [
        ("item.dose", item.dose),
        ("item.when", _when(item, language)),
        (
            "item.duration",
            _duration(item.duration_days, language) if item.duration_days else None,
        ),
        ("item.quantity", item.quantity),
        ("item.preparation", _preparation(item, language)),
        ("item.storage", _storage(item, language)),
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


def _age(patient: Patient, on: date, language: Language) -> str:
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
        RxField(phrase("age", lang), _age(patient, issued_on, lang)),
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
        title=phrase("title", lang),
        revision_note=phrase("revised", lang, version=rx.version) if rx.version > 1 else None,
        clinic_name=clinic.name,
        clinic_lines=clinic_lines,
        doctor_name=doctor.display_name,
        doctor_lines=doctor_lines,
        patient=tuple(people),
        issued_on=RxField(phrase("date", lang), format_date(issued_on, lang)),
        medicines_heading=phrase("medicines", lang),
        medicines=tuple(_medicine(item, lang) for item in rx.items),
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
    )
