"""Permission matrix (PRD §8.1, spec §2) — one table, so a policy change is a visible diff."""

from __future__ import annotations

import pytest

from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.access import ClinicAccess
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.permissions import Permission as P
from mediease_api.domain.identity.permissions import permissions_for
from tests.builders import new_id

OWN, DOC, DESK = Role.OWNER, Role.DOCTOR, Role.FRONT_DESK

# Permission -> roles that hold it (owner without a doctor profile).
MATRIX: dict[P, set[Role]] = {
    P.CLINIC_VIEW: {OWN, DOC, DESK},
    P.DOCTORS_VIEW: {OWN, DOC, DESK},
    P.CLINIC_MANAGE: {OWN},
    P.STAFF_MANAGE: {OWN},
    P.PATIENTS_MANAGE: {OWN, DOC, DESK},
    P.APPOINTMENTS_MANAGE: {OWN, DOC, DESK},
    P.SCHEDULES_MANAGE: {OWN},
    P.QUEUE_MOVE: {OWN, DOC, DESK},
    P.REMINDERS_SCHEDULE: {OWN, DOC, DESK},
    P.CLINICAL_VIEW: {OWN, DOC},
    P.CLINICAL_WRITE: {DOC},
    P.USAGE_METRICS_VIEW: {OWN, DOC},
    P.RX_PRINT: {OWN, DOC, DESK},
    # M6a-P8 (FR-AUD-03): the clinic's audit log, owners only.
    P.AUDIT_VIEW: {OWN},
    # M6d (PRD §8.1, B2): billing for every role; the fee schedule for owners only.
    P.BILLING_MANAGE: {OWN, DOC, DESK},
    P.FEES_MANAGE: {OWN},
}


def test_matrix_covers_every_permission() -> None:
    assert set(MATRIX) == set(P)


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("permission", list(P))
def test_fr_auth_03_prd_permission_matrix(role: Role, permission: P) -> None:
    granted = permission in permissions_for(role, has_doctor_profile=False)
    assert granted is (role in MATRIX[permission])


def test_front_desk_never_gets_clinical_access() -> None:
    granted = permissions_for(DESK, has_doctor_profile=True)
    assert P.CLINICAL_VIEW not in granted and P.CLINICAL_WRITE not in granted


def test_spec_8_owner_who_is_a_doctor_may_write_clinical_records() -> None:
    assert P.CLINICAL_WRITE in permissions_for(OWN, has_doctor_profile=True)
    assert P.CLINICAL_WRITE not in permissions_for(OWN, has_doctor_profile=False)


def test_clinic_access_exposes_its_permissions() -> None:
    access = ClinicAccess(
        membership_id=new_id(),
        clinic_id=new_id(),
        clinic_name="Sample Clinic",
        clinic_status=ClinicStatus.ACTIVE,
        role=OWN,
        has_doctor_profile=True,
    )
    assert P.CLINICAL_WRITE in access.permissions
