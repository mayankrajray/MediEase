"""A prescription explained from its record (M7a-P3; FR-AI-04; spec assistant R10; ADR-0024).

``explain`` turns the patient page of one issued (or superseded) version, built from the database
by ``patient_view``, into plain lines: who wrote it and when, each medicine with how much, when,
how to give, how long, storage, warnings and notes exactly as the page says them, the doctor's
advice and the next visit. The words are the phrasebook's (the same as the patient page) and
the doctor's own text passes through unchanged, so nothing is added, guessed or reworded.

The result also says which numbers and which doctor's words it contains: the after-model guard
rails allow a model's reply only those numbers (``reply_is_grounded``) and take those words out
before looking for advice phrasing (``reply_is_safe``).
"""

from __future__ import annotations

from dataclasses import dataclass

from mediease_api.domain.assistant.guard_rails import numbers_in
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.patient_view import PatientPage

_PHRASES: dict[Language, dict[str, str]] = {
    Language.EN: {
        "intro": "This is what {doctor} wrote on {date} ({clinic}):",
        "historical": (
            "This is an older version (version {version}) of this prescription. A newer version "
            "has replaced it."
        ),
        "medicines": "Medicines:",
        "no_medicines": "There are no medicines on this prescription.",
        "advice": "The doctor's advice:",
        "ask": "If anything is unclear, please ask your clinic{phone}.",
        "phone": " on {phone}",
        "only": "This prescription has {count} medicine(s). Medicine {number} is not on it.",
    },
    Language.HI: {
        "intro": "{doctor} ने {date} को यह लिखा ({clinic}):",
        "historical": (
            "यह इस पर्चे का पुराना संस्करण (संस्करण {version}) है। इसकी जगह एक नया संस्करण आ चुका है।"
        ),
        "medicines": "दवाइयाँ:",
        "no_medicines": "इस पर्चे में कोई दवा नहीं है।",
        "advice": "डॉक्टर की सलाह:",
        "ask": "कुछ भी साफ़ न हो तो कृपया अपने क्लिनिक से पूछें{phone}।",
        "phone": " ({phone})",
        "only": "इस पर्चे में {count} दवा/दवाइयाँ हैं। दवा {number} इसमें नहीं है।",
    },
}


@dataclass(frozen=True, slots=True)
class Explanation:
    text: str
    # FR-AI-04: what a model's reply about this prescription may use.
    numbers: frozenset[str]
    own_words: frozenset[str]


def explain(
    page: PatientPage,
    *,
    historical: bool = False,
    medicine_number: int | None = None,
) -> Explanation:
    """The page's content as plain lines; ``medicine_number`` narrows it to one medicine."""
    say = _PHRASES[page.language]
    lines: list[str] = []
    if historical:
        lines.append(say["historical"].format(version=page.version))
    lines.append(
        say["intro"].format(
            doctor=page.doctor_name, date=page.issued_on.value, clinic=page.clinic_name
        )
    )
    medicines = page.medicines
    if medicine_number is not None:
        medicines = tuple(m for m in page.medicines if m.number == medicine_number)
        if not medicines:
            lines.append(say["only"].format(count=len(page.medicines), number=medicine_number))
    own: set[str] = set()
    if medicines:
        lines.append(say["medicines"])
        for medicine in medicines:
            name = medicine.name
            if medicine.form_strength:
                name = f"{name} ({medicine.form_strength})"
            lines.append(f"{medicine.number}. {name}")
            own.add(medicine.name)
            for field in medicine.fields:
                lines.append(f"   - {field.label}: {field.value}")
                own.add(field.value)
    elif medicine_number is None:
        lines.append(say["no_medicines"])
    if medicine_number is None:
        if page.advice or page.advice_notes:
            lines.append(say["advice"])
            for block in page.advice:
                lines.append(f"   - {block.heading}: {'; '.join(block.entries)}")
                own.update(block.entries)
            if page.advice_notes:
                lines.append(f"   - {page.advice_notes.label}: {page.advice_notes.value}")
                own.add(page.advice_notes.value)
        if page.follow_up:
            lines.append(f"{page.follow_up.label}: {page.follow_up.value}")
    phone = say["phone"].format(phone=page.clinic_phone_e164) if page.clinic_phone_e164 else ""
    lines.append(say["ask"].format(phone=phone))
    text = "\n".join(lines)
    return Explanation(text=text, numbers=numbers_in(text), own_words=frozenset(own))
