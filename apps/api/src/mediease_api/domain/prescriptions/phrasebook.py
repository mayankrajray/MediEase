"""Printed and patient-facing wording in English and Hindi (spec prescriptions R20, D5).

One book for the PDF (M4-P4) and the patient page (M4-P5): every label and every structured
phrase of the vocabulary (``vocabulary.py``) in both languages. What the doctor types (medicine
names, doses, warnings, notes, advice) is never in here and never translated; it is printed as
written.

Phrases are formatting, not clinical advice: they say how a code the doctor chose reads to the
patient. ``{name}`` placeholders take values from the prescription (an amount, a number of days).

**Hindi status (M4-P4 decision 4A):** written for the pilot, *not yet reviewed* by a
native-speaking clinician. That review (L-07) must happen before patients receive Hindi
prescriptions; a correction is a change to one line here. ``HINDI_REVIEWED`` records it.

A phrase missing in Hindi falls back to English, so a gap never blanks a printed line; the
completeness test (``tests/unit/domain/test_phrasebook.py``) fails if one is missing.
"""

from __future__ import annotations

import string
from collections.abc import Mapping

from mediease_api.domain.patients.patient import Language, Sex
from mediease_api.domain.prescriptions.vocabulary import (
    Frequency,
    PreparationCode,
    StorageCode,
    Timing,
)

HINDI_REVIEWED = False

ENGLISH: Mapping[str, str] = {
    # Document and sections
    "title": "Prescription",
    "revised": "Revised prescription (version {version})",
    "medicines": "Medicines",
    "advice": "Advice",
    "advice.diet": "Diet",
    "advice.activity": "Activity",
    "advice.return_if": "Come back immediately if",
    "advice.notes": "Notes",
    "follow_up": "Next visit",
    "footer": "Digitally generated via MediEase",
    "page": "Page {page} of {pages}",
    # Letterhead and people
    "phone": "Phone",
    "registration": "Reg. No. {number}, {council}",
    "patient": "Patient",
    "patient_code": "Patient code",
    "age": "Age",
    "age.years": "{years} years",
    "age.infant": "Under 1 year",
    "sex": "Sex",
    "date": "Date",
    "sex.FEMALE": "Female",
    "sex.MALE": "Male",
    "sex.OTHER": "Other",
    # A medicine line
    "item.dose": "Dose",
    "item.when": "When",
    "item.duration": "How long",
    "item.quantity": "Quantity",
    "item.preparation": "How to give",
    "item.storage": "Storage",
    "item.warnings": "Warnings",
    "item.notes": "Notes",
    "duration.days": "{days} days",
    "duration.day": "1 day",
    # Frequency (vocabulary.Frequency; CUSTOM prints the doctor's text)
    "frequency.1-0-0": "Once a day, in the morning",
    "frequency.0-1-0": "Once a day, in the afternoon",
    "frequency.0-0-1": "Once a day, at night",
    "frequency.1-0-1": "Twice a day, morning and night",
    "frequency.1-1-1": "Three times a day",
    "frequency.1-1-1-1": "Four times a day",
    "frequency.SOS": "Only when needed",
    "frequency.ONCE": "Once only",
    # Timing (vocabulary.Timing)
    "timing.BEFORE_FOOD": "before food",
    "timing.AFTER_FOOD": "after food",
    "timing.WITH_FOOD": "with food",
    "timing.EMPTY_STOMACH": "on an empty stomach",
    "timing.BEDTIME": "at bedtime",
    "timing.ANY": "at any time",
    # Preparation (vocabulary.PreparationCode; CUSTOM prints the doctor's text)
    "preparation.SHAKE_WELL": "Shake well before use",
    "preparation.DILUTE_IN_WATER": "Mix in {amount} of water",
    "preparation.DISSOLVE": "Dissolve in water",
    "preparation.CHEW": "Chew before swallowing",
    "preparation.DO_NOT_CRUSH": "Swallow whole; do not crush or chew",
    # Storage (vocabulary.StorageCode)
    "storage.ROOM_TEMP": "Store at room temperature",
    "storage.REFRIGERATE": "Keep in the fridge",
    "storage.AWAY_FROM_LIGHT": "Keep away from light",
    "storage.DISCARD_AFTER_DAYS": "Throw away {days} days after opening",
    # Months, for dates
    "month.1": "Jan",
    "month.2": "Feb",
    "month.3": "Mar",
    "month.4": "Apr",
    "month.5": "May",
    "month.6": "Jun",
    "month.7": "Jul",
    "month.8": "Aug",
    "month.9": "Sep",
    "month.10": "Oct",
    "month.11": "Nov",
    "month.12": "Dec",
}

HINDI: Mapping[str, str] = {
    "title": "पर्चा",
    "revised": "संशोधित पर्चा (संस्करण {version})",
    "medicines": "दवाइयाँ",
    "advice": "सलाह",
    "advice.diet": "खान-पान",
    "advice.activity": "गतिविधि",
    "advice.return_if": "तुरंत वापस आएँ अगर",
    "advice.notes": "टिप्पणी",
    "follow_up": "अगली जाँच",
    "footer": "MediEase द्वारा डिजिटल रूप से तैयार",
    "page": "पृष्ठ {page} / {pages}",
    "phone": "फ़ोन",
    "registration": "पंजीकरण सं. {number}, {council}",
    "patient": "मरीज़",
    "patient_code": "मरीज़ कोड",
    "age": "उम्र",
    "age.years": "{years} वर्ष",
    "age.infant": "1 वर्ष से कम",
    "sex": "लिंग",
    "date": "दिनांक",
    "sex.FEMALE": "महिला",
    "sex.MALE": "पुरुष",
    "sex.OTHER": "अन्य",
    "item.dose": "खुराक",
    "item.when": "कब लें",
    "item.duration": "कितने दिन",
    "item.quantity": "मात्रा",
    "item.preparation": "कैसे दें",
    "item.storage": "कैसे रखें",
    "item.warnings": "सावधानी",
    "item.notes": "टिप्पणी",
    "duration.days": "{days} दिन",
    "duration.day": "1 दिन",
    "frequency.1-0-0": "दिन में एक बार, सुबह",
    "frequency.0-1-0": "दिन में एक बार, दोपहर",
    "frequency.0-0-1": "दिन में एक बार, रात को",
    "frequency.1-0-1": "दिन में दो बार, सुबह और रात",
    "frequency.1-1-1": "दिन में तीन बार",
    "frequency.1-1-1-1": "दिन में चार बार",
    "frequency.SOS": "केवल ज़रूरत होने पर",
    "frequency.ONCE": "केवल एक बार",
    "timing.BEFORE_FOOD": "खाने से पहले",
    "timing.AFTER_FOOD": "खाने के बाद",
    "timing.WITH_FOOD": "खाने के साथ",
    "timing.EMPTY_STOMACH": "खाली पेट",
    "timing.BEDTIME": "सोते समय",
    "timing.ANY": "किसी भी समय",
    "preparation.SHAKE_WELL": "इस्तेमाल से पहले अच्छी तरह हिलाएँ",
    "preparation.DILUTE_IN_WATER": "{amount} पानी में मिलाएँ",
    "preparation.DISSOLVE": "पानी में घोलें",
    "preparation.CHEW": "चबाकर निगलें",
    "preparation.DO_NOT_CRUSH": "पूरा निगलें; तोड़ें या चबाएँ नहीं",
    "storage.ROOM_TEMP": "कमरे के तापमान पर रखें",
    "storage.REFRIGERATE": "फ़्रिज में रखें",
    "storage.AWAY_FROM_LIGHT": "रोशनी से दूर रखें",
    "storage.DISCARD_AFTER_DAYS": "खोलने के {days} दिन बाद फेंक दें",
    "month.1": "जनवरी",
    "month.2": "फ़रवरी",
    "month.3": "मार्च",
    "month.4": "अप्रैल",
    "month.5": "मई",
    "month.6": "जून",
    "month.7": "जुलाई",
    "month.8": "अगस्त",
    "month.9": "सितंबर",
    "month.10": "अक्टूबर",
    "month.11": "नवंबर",
    "month.12": "दिसंबर",
}

BOOKS: Mapping[Language, Mapping[str, str]] = {Language.EN: ENGLISH, Language.HI: HINDI}


def required_keys() -> frozenset[str]:
    """Every key the documents use: the labels plus one per vocabulary code."""
    codes = (
        {f"frequency.{f.value}" for f in Frequency if f is not Frequency.CUSTOM}
        | {f"timing.{t.value}" for t in Timing}
        | {f"preparation.{p.value}" for p in PreparationCode if p is not PreparationCode.CUSTOM}
        | {f"storage.{s.value}" for s in StorageCode}
        | {f"sex.{s.value}" for s in Sex if s is not Sex.UNDISCLOSED}
        | {f"month.{m}" for m in range(1, 13)}
    )
    return frozenset(codes | set(ENGLISH))


def placeholders(text: str) -> frozenset[str]:
    return frozenset(name for _, name, _, _ in string.Formatter().parse(text) if name)


def phrase(key: str, language: Language, **params: object) -> str:
    """The wording of ``key``; Hindi falls back to English for a missing phrase."""
    text = BOOKS[language].get(key) or ENGLISH[key]
    return text.format(**params) if params else text
