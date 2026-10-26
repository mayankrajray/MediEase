"""The listing rules and the discoverability rule (M6c-P4; spec R51-R55)."""

from __future__ import annotations

from dataclasses import replace

from mediease_api.domain.clinics.clinic import Clinic, ClinicStatus
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.clinics.listing import (
    DoctorListing,
    DoctorProblem,
    ListingProblem,
    is_discoverable,
    listing_problems,
)
from mediease_api.domain.clinics.verification import VerificationSource
from tests.builders import NOW, a_clinic, a_doctor


def _ready() -> tuple[Clinic, Doctor]:
    clinic = a_clinic()
    clinic.activate(active_owner_count=1, now=NOW)
    clinic.update_details(
        now=NOW, address_line="1 Sample Road", city="Sample City", pincode="560001"
    )
    clinic.verify(by=clinic.id, source=VerificationSource.OPS_CHECK, now=NOW)
    doctor = a_doctor(clinic.id)
    doctor.verify(by=clinic.id, source=VerificationSource.OPS_CHECK, now=NOW)
    doctor.set_visible(True, now=NOW)
    return clinic, doctor


def test_r51_a_ready_clinic_has_no_problem_and_is_discoverable_once_listed() -> None:
    clinic, doctor = _ready()
    doctors = [DoctorListing(doctor, has_schedule=True)]
    assert listing_problems(clinic, doctors) == ()
    assert not is_discoverable(clinic, doctors)
    clinic.set_listed(True, now=NOW)
    assert is_discoverable(clinic, doctors)


def test_r51_each_requirement_is_reported_in_order() -> None:
    clinic = a_clinic()
    clinic.address_line = None
    doctor = a_doctor(clinic.id)
    assert listing_problems(clinic, [DoctorListing(doctor, has_schedule=False)]) == (
        ListingProblem.NOT_ACTIVE,
        ListingProblem.NOT_VERIFIED,
        ListingProblem.ADDRESS_MISSING,
        ListingProblem.NO_BOOKABLE_DOCTOR,
    )
    assert DoctorListing(doctor, has_schedule=False).problems == (
        DoctorProblem.NOT_VERIFIED,
        DoctorProblem.NO_SCHEDULE,
        DoctorProblem.HIDDEN,
    )


def test_r54_r55_a_suspended_clinic_or_a_hidden_doctor_ends_discoverability() -> None:
    clinic, doctor = _ready()
    clinic.set_listed(True, now=NOW)
    assert not is_discoverable(clinic, [DoctorListing(doctor, has_schedule=False)])
    assert not is_discoverable(
        clinic, [DoctorListing(replace(doctor, visible=False), has_schedule=True)]
    )
    inactive = DoctorListing(replace(doctor, is_active=False), has_schedule=True)
    assert not inactive.is_shown and not inactive.can_be_visible
    clinic.suspend(now=NOW)
    assert clinic.status is ClinicStatus.SUSPENDED
    assert listing_problems(clinic, [DoctorListing(doctor, has_schedule=True)]) == (
        ListingProblem.NOT_ACTIVE,
    )
