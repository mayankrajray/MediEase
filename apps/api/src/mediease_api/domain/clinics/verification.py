"""Verification and listing words shared by clinics and doctors (M6c-P3, P4; FR-ONB-09, 10).

Verification is recorded by a MediEase reviewer, per clinic and per doctor, with its source; it is
never inferred from a status (PRD §8.14). Listing is the owner's choice, allowed only when the
listing requirements hold (``domain/onboarding/listing.py``).
"""

from __future__ import annotations

from enum import StrEnum


class VerificationSource(StrEnum):
    # Approval of a clinic application (FR-ONB-04).
    APPLICATION = "APPLICATION"
    # A reviewer's check of an ops-created clinic or doctor (FR-ONB-06).
    OPS_CHECK = "OPS_CHECK"


# P5 (FR-DIS-03): the languages a doctor's profile may list.
LANGUAGES: tuple[str, ...] = (
    "English",
    "Hindi",
    "Marathi",
    "Gujarati",
    "Bengali",
    "Tamil",
    "Telugu",
    "Kannada",
    "Malayalam",
    "Punjabi",
    "Odia",
    "Urdu",
    "Assamese",
)
MAX_FEE_PAISE = 10_000_00
