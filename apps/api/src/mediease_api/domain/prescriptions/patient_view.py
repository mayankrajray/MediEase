"""What the patient page shows (spec prescriptions R11, R12, R19, R20, §6; AC2; M4-P5).

Built from the chain's **latest issued** version (R11) in the language the page asks for: the
patient's saved preference, or the page's English / हिन्दी switch (R19). ``build_preview`` gives
the same page for a draft, as it would be if issued today (M4-P6 decision 3A). Labels and
structured phrases come from the phrasebook; everything the doctor wrote is passed through
exactly as written (R20). The patient's own name, code and age are left out: the person
holding the phone knows them, and a forwarded link then shows less.

One card per medicine with the spec §6 headings, in the order a patient reads them: *How much*,
*When to take*, *How to give*, *For how long*, *Storage*, then warnings and notes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.document import (
    RxAdvice,
    RxField,
    duration_text,
    format_date,
    preparation_text,
    storage_text,
    when_text,
)
from mediease_api.domain.prescriptions.errors import NotDraft
from mediease_api.domain.prescriptions.phrasebook import phrase
from mediease_api.domain.prescriptions.prescription import (
    ClinicSnapshot,
    DoctorSnapshot,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    latest_issued,
)
from mediease_api.domain.shared.time import local_date


@dataclass(frozen=True, slots=True)
class PatientMedicine:
    number: int
    name: str
    form_strength: str | None
    fields: tuple[RxField, ...]


@dataclass(frozen=True, slots=True)
class PatientPage:
    language: Language
    version: int
    clinic_name: str
    clinic_phone_e164: str | None
    call_label: str
    doctor_name: str
    doctor_lines: tuple[str, ...]
    issued_on: RxField
    updated_note: str | None
    medicines_heading: str
    medicines: tuple[PatientMedicine, ...]
    advice_heading: str
    advice: tuple[RxAdvice, ...]
    advice_notes: RxField | None
    follow_up: RxField | None


def _card(item: PrescriptionItem, lang: Language) -> PatientMedicine:
    values = [
        ("page.how_much", item.dose),
        ("page.when", when_text(item, lang)),
        ("page.how_to_give", preparation_text(item, lang)),
        ("page.how_long", duration_text(item.duration_days, lang) if item.duration_days else None),
        ("item.quantity", item.quantity),
        ("item.storage", storage_text(item, lang)),
        ("item.warnings", item.warnings),
        ("item.notes", item.notes),
    ]
    return PatientMedicine(
        number=item.position,
        name=item.medicine_name,
        form_strength=" · ".join(v for v in (item.form, item.strength) if v) or None,
        fields=tuple(RxField(phrase(key, lang), v) for key, v in values if v),
    )


def build_patient_view(
    chain: Sequence[Prescription], *, language: Language, timezone: str
) -> PatientPage | None:
    """The page for this chain, or ``None`` while nothing in it is issued."""
    rx = latest_issued(chain)
    if rx is None:
        return None
    assert rx.issued_at and rx.doctor_snapshot and rx.clinic_snapshot
    return _page(
        rx,
        doctor=rx.doctor_snapshot,
        clinic=rx.clinic_snapshot,
        issued_on=local_date(rx.issued_at, timezone),
        older=any(p.status is PrescriptionStatus.SUPERSEDED for p in chain),
        language=language,
    )


def build_preview(
    draft: Prescription,
    *,
    doctor: Doctor,
    clinic: Clinic,
    language: Language,
    today: date,
) -> PatientPage:
    """M4-P6 decision 3A: the page a draft would give if issued today, with the doctor and
    clinic as they are now (issuing copies exactly these); ``RX_DOCTOR_INCOMPLETE`` as issuing
    would be. An issued draft's revision shows the update banner, as the page will."""
    if not draft.is_draft:
        raise NotDraft(draft.status.value)
    return _page(
        draft,
        doctor=DoctorSnapshot.of(doctor),
        clinic=ClinicSnapshot.of(clinic),
        issued_on=today,
        older=draft.version > 1,
        language=language,
    )


def _page(
    rx: Prescription,
    *,
    doctor: DoctorSnapshot,
    clinic: ClinicSnapshot,
    issued_on: date,
    older: bool,
    language: Language,
) -> PatientPage:
    lang = language
    registration = phrase(
        "registration",
        lang,
        number=doctor.registration_number,
        council=doctor.registration_council,
    )
    return PatientPage(
        language=lang,
        version=rx.version,
        clinic_name=clinic.name,
        clinic_phone_e164=clinic.phone_e164,
        call_label=phrase("page.call", lang),
        doctor_name=doctor.display_name,
        doctor_lines=tuple(v for v in (doctor.qualification, registration) if v),
        issued_on=RxField(phrase("date", lang), format_date(issued_on, lang)),
        updated_note=(
            phrase("page.updated", lang, date=format_date(issued_on, lang)) if older else None
        ),
        medicines_heading=phrase("medicines", lang),
        medicines=tuple(_card(item, lang) for item in rx.items),
        advice_heading=phrase("advice", lang),
        advice=tuple(
            RxAdvice(phrase(key, lang), entries)
            for key, entries in (
                ("advice.diet", rx.advice.diet),
                ("advice.activity", rx.advice.activity),
                ("advice.return_if", rx.advice.return_if),
            )
            if entries
        ),
        advice_notes=(
            RxField(phrase("advice.notes", lang), rx.advice.notes) if rx.advice.notes else None
        ),
        follow_up=(
            RxField(phrase("follow_up", lang), format_date(rx.follow_up_date, lang))
            if rx.follow_up_date
            else None
        ),
    )
