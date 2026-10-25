"""The published lists an application chooses from (M6c-P1; spec clinic-onboarding R4).

Councils are the bodies a registration number belongs to: the National Medical Commission and
the state medical councils, as their names appear on certificates. Specialties are the clinic's
broad areas, shown later on profiles and used by search (P5, P6). Both are data, not rules: a
council or specialty added here needs no migration.
"""

from __future__ import annotations

COUNCILS: tuple[str, ...] = (
    "National Medical Commission",
    "Andhra Pradesh Medical Council",
    "Arunachal Pradesh Medical Council",
    "Assam Medical Council",
    "Bihar Council of Medical Registration",
    "Chhattisgarh Medical Council",
    "Delhi Medical Council",
    "Goa Medical Council",
    "Gujarat Medical Council",
    "Haryana Medical Council",
    "Himachal Pradesh Medical Council",
    "Jammu and Kashmir Medical Council",
    "Jharkhand Medical Council",
    "Karnataka Medical Council",
    "Madhya Pradesh Medical Council",
    "Maharashtra Medical Council",
    "Manipur Medical Council",
    "Meghalaya Medical Council",
    "Mizoram Medical Council",
    "Nagaland Medical Council",
    "Odisha Council of Medical Registration",
    "Punjab Medical Council",
    "Rajasthan Medical Council",
    "Sikkim Medical Council",
    "Tamil Nadu Medical Council",
    "Telangana State Medical Council",
    "Travancore-Cochin Medical Council (Kerala)",
    "Tripura State Medical Council",
    "Uttar Pradesh Medical Council",
    "Uttarakhand Medical Council",
    "West Bengal Medical Council",
)

SPECIALTIES: tuple[str, ...] = (
    "General Medicine",
    "Family Medicine",
    "Paediatrics",
    "Obstetrics and Gynaecology",
    "Dermatology",
    "ENT",
    "Ophthalmology",
    "Orthopaedics",
    "Cardiology",
    "Diabetology",
    "Endocrinology",
    "Gastroenterology",
    "Neurology",
    "Nephrology",
    "Pulmonology",
    "Psychiatry",
    "Urology",
    "General Surgery",
)

_COUNCILS = frozenset(COUNCILS)
_SPECIALTIES = frozenset(SPECIALTIES)


def is_council(name: str) -> bool:
    return name in _COUNCILS


def is_specialty(name: str) -> bool:
    return name in _SPECIALTIES
