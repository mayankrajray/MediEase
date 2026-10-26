"""The directory listing and the one discoverability rule (M6c-P4; FR-ONB-09, 10; spec R50-R58).

A clinic is **discoverable** (in search, on indexable profiles) only when it is ``ACTIVE``,
verified, its owner has listed it, and nothing in ``listing_problems`` stands in the way. The
public page (``has_public_page``) needs less: ``ACTIVE`` and verified (FR-DIS-07: a clinic may
take requests from its own link without being in the directory).

The rules are pure: the caller passes each doctor with whether it has a weekly schedule.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.shared.errors import DomainError


class ListingProblem(StrEnum):
    """R51: why a clinic cannot be in the directory, in the order the owner fixes them."""

    NOT_ACTIVE = "NOT_ACTIVE"
    NOT_VERIFIED = "NOT_VERIFIED"
    ADDRESS_MISSING = "ADDRESS_MISSING"
    NO_BOOKABLE_DOCTOR = "NO_BOOKABLE_DOCTOR"


class DoctorProblem(StrEnum):
    """R53: why a doctor is not shown (visible needs active and verified)."""

    INACTIVE = "INACTIVE"
    NOT_VERIFIED = "NOT_VERIFIED"
    NO_SCHEDULE = "NO_SCHEDULE"
    HIDDEN = "HIDDEN"


@dataclass(frozen=True, slots=True)
class DoctorListing:
    doctor: Doctor
    has_schedule: bool

    @property
    def problems(self) -> tuple[DoctorProblem, ...]:
        found: list[DoctorProblem] = []
        if not self.doctor.is_active:
            found.append(DoctorProblem.INACTIVE)
        if not self.doctor.is_verified:
            found.append(DoctorProblem.NOT_VERIFIED)
        if not self.has_schedule:
            found.append(DoctorProblem.NO_SCHEDULE)
        if not self.doctor.visible:
            found.append(DoctorProblem.HIDDEN)
        return tuple(found)

    @property
    def can_be_visible(self) -> bool:
        """R53: the switch needs an active, verified doctor."""
        return self.doctor.is_active and self.doctor.is_verified

    @property
    def is_shown(self) -> bool:
        """R54: on the public page and in the directory: active, verified and visible. A doctor
        without a schedule is shown but has no times."""
        return self.can_be_visible and self.doctor.visible


def listing_problems(
    clinic: Clinic, doctors: Sequence[DoctorListing]
) -> tuple[ListingProblem, ...]:
    """R51: every requirement the clinic does not meet yet (empty: it may be listed)."""
    found: list[ListingProblem] = []
    if clinic.status is not ClinicStatus.ACTIVE:
        found.append(ListingProblem.NOT_ACTIVE)
    if not clinic.is_verified:
        found.append(ListingProblem.NOT_VERIFIED)
    if not (clinic.address_line and clinic.city and clinic.pincode):
        found.append(ListingProblem.ADDRESS_MISSING)
    if not any(d.is_shown and d.has_schedule for d in doctors):
        found.append(ListingProblem.NO_BOOKABLE_DOCTOR)
    return tuple(found)


def is_discoverable(clinic: Clinic, doctors: Sequence[DoctorListing]) -> bool:
    """R55: the one discoverability rule, used by profiles, the sitemap and search."""
    return clinic.listed and not listing_problems(clinic, doctors)


class ListingBlocked(DomainError):
    """R52: the clinic cannot be listed until these are fixed (``details.problems``)."""

    code = "CLN_LISTING_BLOCKED"

    def __init__(self, problems: Sequence[ListingProblem]) -> None:
        super().__init__(
            "The clinic cannot be listed yet.", problems=",".join(p.value for p in problems)
        )


class DoctorNotShowable(DomainError):
    """R53: only an active doctor verified by MediEase can be made visible."""

    code = "CLN_DOCTOR_NOT_VERIFIED"

    def __init__(self) -> None:
        super().__init__("Only an active doctor verified by MediEase can be shown.")
