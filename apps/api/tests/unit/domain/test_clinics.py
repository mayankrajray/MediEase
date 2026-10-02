"""Clinic and Doctor rules (FR-ORG-01, FR-ORG-02; spec I1, I3)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from mediease_api.domain.clinics.clinic import (
    DEFAULT_TIMEZONE,
    Clinic,
    ClinicOwnerRequired,
    ClinicStatus,
)
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from tests.builders import LATER, NOW, a_clinic, a_doctor

# --- Clinic ---------------------------------------------------------------------------


def test_fr_org_01_new_clinic_is_onboarding_in_ist_by_default() -> None:
    clinic = Clinic.create(id=uuid4(), name="  Sample Clinic ", slug="sample-clinic", now=NOW)
    assert clinic.status is ClinicStatus.ONBOARDING
    assert clinic.timezone == DEFAULT_TIMEZONE == "Asia/Kolkata"
    assert clinic.name == "Sample Clinic"
    assert clinic.created_at == clinic.updated_at == NOW
    assert clinic.specialties == ()


def test_fr_org_01_specialties_are_trimmed_and_deduplicated() -> None:
    clinic = a_clinic(specialties=(" Paediatrics", "Paediatrics ", "ENT"))
    assert clinic.specialties == ("Paediatrics", "ENT")


@pytest.mark.parametrize(
    "slug", ["ab", "Sample", "sample_clinic", "-sample", "sample--x", "x" * 64]
)
def test_invalid_slugs_are_rejected(slug: str) -> None:
    with pytest.raises(InvalidValue) as excinfo:
        a_clinic(slug=slug)
    assert excinfo.value.field == "slug"


@pytest.mark.parametrize("tz", ["Mars/Olympus", "../etc/passwd", ""])
def test_unknown_timezones_are_rejected(tz: str) -> None:
    with pytest.raises(InvalidValue) as excinfo:
        a_clinic(timezone=tz)
    assert excinfo.value.field == "timezone"


@pytest.mark.parametrize("pincode", ["012345", "56001", "5600011", "56000A"])
def test_invalid_pincodes_are_rejected(pincode: str) -> None:
    with pytest.raises(InvalidValue) as excinfo:
        a_clinic(pincode=pincode)
    assert excinfo.value.field == "pincode"


def test_blank_name_is_rejected() -> None:
    with pytest.raises(InvalidValue) as excinfo:
        a_clinic(name="   ")
    assert excinfo.value.field == "name"


def test_i1_clinic_cannot_activate_without_an_active_owner() -> None:
    clinic = a_clinic()
    with pytest.raises(ClinicOwnerRequired) as excinfo:
        clinic.activate(active_owner_count=0, now=LATER)
    assert excinfo.value.code == "CLN_OWNER_REQUIRED"
    assert clinic.status is ClinicStatus.ONBOARDING
    assert clinic.updated_at == NOW


def test_clinic_lifecycle_onboarding_active_suspended_active() -> None:
    clinic = a_clinic()
    clinic.activate(active_owner_count=1, now=LATER)
    assert clinic.status is ClinicStatus.ACTIVE
    assert clinic.updated_at == LATER

    clinic.suspend(now=LATER)
    assert clinic.status is ClinicStatus.SUSPENDED

    clinic.activate(active_owner_count=2, now=LATER)
    assert clinic.status is ClinicStatus.ACTIVE


def test_illegal_clinic_transitions_raise() -> None:
    clinic = a_clinic()
    with pytest.raises(InvalidTransition) as excinfo:
        clinic.suspend(now=LATER)
    assert excinfo.value.code == "CLN_INVALID_TRANSITION"
    assert excinfo.value.details == {"entity": "clinic", "state": "ONBOARDING", "action": "suspend"}

    clinic.activate(active_owner_count=1, now=LATER)
    with pytest.raises(InvalidTransition):
        clinic.activate(active_owner_count=1, now=LATER)


def test_transition_with_a_bad_timestamp_changes_nothing() -> None:
    clinic = a_clinic()
    naive = NOW.replace(tzinfo=None)
    with pytest.raises(InvalidValue):
        clinic.activate(active_owner_count=1, now=naive)
    assert clinic.status is ClinicStatus.ONBOARDING


# --- Doctor ---------------------------------------------------------------------------


def test_fr_org_02_doctor_has_registration_details() -> None:
    clinic_id = uuid4()
    doctor = Doctor.create(
        id=uuid4(),
        clinic_id=clinic_id,
        display_name=" Dr. A. Sample ",
        qualification="MBBS, MD",
        registration_number="REG-00001",
        registration_council="Sample State Medical Council",
        specialty="  ",
        now=NOW,
    )
    assert doctor.display_name == "Dr. A. Sample"
    assert doctor.clinic_id == clinic_id
    assert doctor.user_id is None
    assert doctor.specialty is None
    assert doctor.is_active


@pytest.mark.parametrize("field", ["qualification", "registration_number", "registration_council"])
def test_i3_doctor_requires_prescription_details(field: str) -> None:
    with pytest.raises(InvalidValue) as excinfo:
        a_doctor(uuid4(), **{field: " "})
    assert excinfo.value.field == field


def test_doctor_deactivates_once() -> None:
    doctor = a_doctor(uuid4())
    doctor.deactivate(now=LATER)
    assert not doctor.is_active
    assert doctor.updated_at == LATER
    with pytest.raises(InvalidTransition):
        doctor.deactivate(now=LATER)
