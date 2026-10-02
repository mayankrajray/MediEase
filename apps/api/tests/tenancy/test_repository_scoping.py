"""Tenancy isolation at the repository layer (NFR-08, ADR-0003, spec R8).

Permanent suite: two clinics, A and B, each with doctors and memberships.
Repositories bound to clinic A must behave as if clinic B's rows do not
exist — for reads, lists, counts and writes — and must refuse an entity that
belongs to B. From M1-P3 the same isolation is proved again at the HTTP level.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from mediease_api.adapters.db.models import Base
from mediease_api.adapters.db.repositories import (
    SqlAlchemyDoctorRepository,
    SqlAlchemyMembershipRepository,
)
from mediease_api.adapters.db.tenancy import TenancyViolation, TenantScopedRepository
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import ClinicMembership, Role
from mediease_api.domain.shared.errors import NotFound
from tests.builders import LATER, a_clinic, a_doctor, a_membership, a_user
from tests.conftest import UowFactory


@dataclass(frozen=True)
class Tenant:
    clinic_id: UUID
    doctor: Doctor
    owner: ClinicMembership


@pytest.fixture
def two_clinics(uow_factory: UowFactory) -> tuple[Tenant, Tenant]:
    """Clinics A and B, each with one doctor and one active owner."""
    tenants = []
    with uow_factory() as uow:
        for _ in range(2):
            clinic, owner = a_clinic(), a_user()
            uow.clinics.add(clinic)
            uow.users.add(owner)
            staff = uow.tenant(clinic.id)
            doctor = a_doctor(clinic.id, user_id=owner.id)
            membership = a_membership(clinic.id, owner.id, Role.OWNER)
            staff.doctors.add(doctor)
            staff.memberships.add(membership)
            tenants.append(Tenant(clinic.id, doctor, membership))
        uow.commit()
    return tenants[0], tenants[1]


def test_nfr_08_clinic_a_cannot_read_clinic_b_doctors(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    with uow_factory() as uow:
        doctors = uow.tenant(a.clinic_id).doctors
        assert doctors.get(b.doctor.id) is None
        assert doctors.get(a.doctor.id) == a.doctor
        assert [d.id for d in doctors.list()] == [a.doctor.id]


def test_nfr_08_clinic_a_cannot_read_clinic_b_memberships(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    with uow_factory() as uow:
        memberships = uow.tenant(a.clinic_id).memberships
        assert memberships.get(b.owner.id) is None
        assert memberships.get_for_user(b.owner.user_id) is None
        assert [m.id for m in memberships.list()] == [a.owner.id]
        assert memberships.count_active_owners() == 1


def test_nfr_08_identity_map_does_not_leak_across_scopes(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    # Clinic B's rows are already loaded in this session; A's scope still hides them.
    a, b = two_clinics
    with uow_factory() as uow:
        assert uow.tenant(b.clinic_id).doctors.get(b.doctor.id) is not None
        assert uow.tenant(b.clinic_id).memberships.get(b.owner.id) is not None
        assert uow.tenant(a.clinic_id).doctors.get(b.doctor.id) is None
        assert uow.tenant(a.clinic_id).memberships.get(b.owner.id) is None


def test_r8_clinic_a_cannot_update_clinic_b_rows(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    with uow_factory() as uow:
        staff_a = uow.tenant(a.clinic_id)
        # An entity forged with A's clinic_id but B's row ID is simply not found.
        forged_doctor = Doctor(**{**_fields(b.doctor), "clinic_id": a.clinic_id})
        with pytest.raises(NotFound) as excinfo:
            staff_a.doctors.update(forged_doctor)
        assert excinfo.value.details == {"entity": "doctor"}

        forged_membership = ClinicMembership(**{**_fields(b.owner), "clinic_id": a.clinic_id})
        forged_membership.deactivate(active_owner_count=2, now=LATER)
        with pytest.raises(NotFound):
            staff_a.memberships.update(forged_membership)
        uow.commit()

    with uow_factory() as uow:
        assert uow.tenant(b.clinic_id).doctors.get(b.doctor.id) == b.doctor
        assert uow.tenant(b.clinic_id).memberships.get(b.owner.id) == b.owner


def test_repositories_refuse_entities_of_another_clinic(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    with uow_factory() as uow:
        staff_a = uow.tenant(a.clinic_id)
        with pytest.raises(TenancyViolation):
            staff_a.doctors.add(a_doctor(b.clinic_id))
        with pytest.raises(TenancyViolation):
            staff_a.doctors.update(b.doctor)
        with pytest.raises(TenancyViolation):
            staff_a.memberships.add(a_membership(b.clinic_id, b.owner.user_id))
        with pytest.raises(TenancyViolation):
            staff_a.memberships.update(b.owner)


def test_unknown_clinic_scope_sees_nothing(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    with uow_factory() as uow:
        staff = uow.tenant(uuid4())
        assert staff.doctors.list() == []
        assert staff.memberships.list() == []
        assert staff.memberships.count_active_owners() == 0


def test_every_tenant_table_has_a_scoped_repository() -> None:
    """A new table with clinic_id must get a TenantScopedRepository (and tests here)."""
    tenant_tables = {
        table.name for table in Base.metadata.sorted_tables if "clinic_id" in table.columns
    }
    scoped_tables = {
        repo.model.__table__.name  # type: ignore[attr-defined]
        for repo in TenantScopedRepository.__subclasses__()
    }
    assert tenant_tables == scoped_tables == {"doctors", "clinic_memberships"}
    assert {SqlAlchemyDoctorRepository, SqlAlchemyMembershipRepository} == set(
        TenantScopedRepository.__subclasses__()
    )


def _fields(entity: object) -> dict[str, object]:
    return {name: getattr(entity, name) for name in entity.__slots__}  # type: ignore[attr-defined]
