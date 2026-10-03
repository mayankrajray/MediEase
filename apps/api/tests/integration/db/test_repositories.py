"""Repositories and unit of work against real PostgreSQL (ADR-0003, ADR-0004).

Round-trips every entity through its repository, proves the unit of work's
transaction boundaries, and that the database itself enforces the invariants
only it can see (I2 and the users constraints).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.membership import MembershipStatus, Role
from mediease_api.domain.identity.user import UserStatus
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.unit_of_work import UnitOfWork
from tests.builders import LATER, a_clinic, a_doctor, a_membership, a_user
from tests.conftest import UowFactory

# --- Round trips ------------------------------------------------------------------------------


def test_fr_org_01_clinic_round_trip_and_update(uow_factory: UowFactory) -> None:
    clinic = a_clinic(specialties=("Paediatrics", "ENT"))
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.commit()

    with uow_factory() as uow:
        assert uow.clinics.get(clinic.id) == clinic
        assert uow.clinics.get_by_slug(clinic.slug) == clinic
        assert uow.clinics.get(uuid4()) is None
        assert uow.clinics.get_by_slug("no-such-clinic") is None

        clinic.activate(active_owner_count=1, now=LATER)
        uow.clinics.update(clinic)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.clinics.get(clinic.id)
        assert stored is not None
        assert stored.status is ClinicStatus.ACTIVE
        assert stored.updated_at == LATER
        assert stored.created_at.tzinfo is not None


def test_user_round_trip_and_lookup_by_identifier(uow_factory: UowFactory) -> None:
    user = a_user()
    phone_only = a_user(email=None)
    with uow_factory() as uow:
        uow.users.add(user)
        uow.users.add(phone_only)
        uow.commit()

    with uow_factory() as uow:
        assert uow.users.get(user.id) == user
        assert user.email is not None and user.phone is not None
        assert uow.users.get_by_email(user.email) == user
        assert uow.users.get_by_phone(user.phone) == user
        assert uow.users.get(phone_only.id) == phone_only
        assert uow.users.get_by_email(EmailAddress.parse("nobody@example.test")) is None
        assert uow.users.get_by_phone(PhoneNumber.parse("9000099999")) is None

        user.disable(now=LATER)
        uow.users.update(user)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.users.get(user.id)
        assert stored is not None and stored.status is UserStatus.DISABLED


def test_fr_org_02_doctor_round_trip_list_and_update(uow_factory: UowFactory) -> None:
    clinic, owner = a_clinic(), a_user()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(owner)
        staff = uow.tenant(clinic.id)
        first = a_doctor(clinic.id, user_id=owner.id)
        second = a_doctor(clinic.id, specialty="Paediatrics")
        staff.doctors.add(first)
        staff.doctors.add(second)
        uow.commit()

    with uow_factory() as uow:
        staff = uow.tenant(clinic.id)
        assert staff.doctors.get(first.id) == first
        assert [d.id for d in staff.doctors.list()] == [first.id, second.id]

        second.deactivate(now=LATER)
        staff.doctors.update(second)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.tenant(clinic.id).doctors.get(second.id)
        assert stored is not None and not stored.is_active


def test_fr_org_03_membership_round_trip_and_owner_count(uow_factory: UowFactory) -> None:
    clinic = a_clinic()
    owner, doctor, desk, invited = a_user(), a_user(), a_user(), a_user()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        for user in (owner, doctor, desk, invited):
            uow.users.add(user)
        staff = uow.tenant(clinic.id)
        owner_m = a_membership(clinic.id, owner.id, Role.OWNER)
        doctor_m = a_membership(clinic.id, doctor.id, Role.DOCTOR)
        desk_m = a_membership(clinic.id, desk.id, Role.FRONT_DESK)
        invited_m = a_membership(clinic.id, invited.id, Role.OWNER, active=False)
        for membership in (owner_m, doctor_m, desk_m, invited_m):
            staff.memberships.add(membership)
        uow.commit()

    with uow_factory() as uow:
        staff = uow.tenant(clinic.id)
        assert staff.memberships.get(owner_m.id) == owner_m
        assert staff.memberships.get_for_user(desk.id) == desk_m
        assert staff.memberships.get_for_user(uuid4()) is None
        assert len(staff.memberships.list()) == 4
        # The invited owner does not count until they activate (I1, R9).
        assert staff.memberships.count_active_owners() == 1

        doctor_m.change_role(Role.OWNER, active_owner_count=1, now=LATER)
        staff.memberships.update(doctor_m)
        assert staff.memberships.count_active_owners() == 2
        desk_m.deactivate(active_owner_count=2, now=LATER)
        staff.memberships.update(desk_m)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.tenant(clinic.id).memberships.get(desk_m.id)
        assert stored is not None and stored.status is MembershipStatus.DEACTIVATED


def test_update_of_an_unknown_entity_is_not_found(uow_factory: UowFactory) -> None:
    clinic = a_clinic()
    with uow_factory() as uow:
        with pytest.raises(NotFound) as excinfo:
            uow.clinics.update(clinic)
        assert excinfo.value.code == "REQ_NOT_FOUND"
        with pytest.raises(NotFound):
            uow.users.update(a_user())
        uow.clinics.add(clinic)
        with pytest.raises(NotFound):
            uow.tenant(clinic.id).doctors.update(a_doctor(clinic.id))
        with pytest.raises(NotFound):
            uow.tenant(clinic.id).memberships.update(a_membership(clinic.id, uuid4()))


# --- Unit of work ----------------------------------------------------------------------------


def test_leaving_without_commit_rolls_back(uow_factory: UowFactory) -> None:
    clinic = a_clinic()
    with uow_factory() as uow:
        uow.clinics.add(clinic)

    with uow_factory() as uow:
        assert uow.clinics.get(clinic.id) is None


def test_an_exception_rolls_back_the_whole_unit(uow_factory: UowFactory) -> None:
    clinic, user = a_clinic(), a_user()
    with pytest.raises(RuntimeError), uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(user)
        raise RuntimeError("use case failed half way")

    with uow_factory() as uow:
        assert uow.clinics.get(clinic.id) is None
        assert uow.users.get(user.id) is None


def test_explicit_rollback_discards_uncommitted_changes(uow_factory: UowFactory) -> None:
    kept, discarded = a_clinic(), a_clinic()
    with uow_factory() as uow:
        uow.clinics.add(kept)
        uow.commit()
        uow.clinics.add(discarded)
        uow.rollback()
        uow.commit()

    with uow_factory() as uow:
        assert uow.clinics.get(kept.id) is not None
        assert uow.clinics.get(discarded.id) is None


def test_unit_of_work_is_reusable_but_not_reentrant(uow_factory: UowFactory) -> None:
    uow = uow_factory()
    with pytest.raises(RuntimeError, match="not open"):
        _ = uow.clinics
    with uow, pytest.raises(RuntimeError, match="already open"), uow:
        pass
    with uow:  # a second, independent transaction
        assert uow.clinics.get(uuid4()) is None
    with pytest.raises(RuntimeError, match="not open"):
        uow.commit()


def test_unit_of_work_satisfies_the_port(uow_factory: UowFactory) -> None:

    uow: UnitOfWork = uow_factory()
    assert isinstance(uow, SqlAlchemyUnitOfWork)


# --- Database constraints ----------------------------------------------------------------------


def test_i2_one_membership_per_user_per_clinic(uow_factory: UowFactory) -> None:
    clinic, user = a_clinic(), a_user()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(user)
        staff = uow.tenant(clinic.id)
        staff.memberships.add(a_membership(clinic.id, user.id, Role.DOCTOR))
        with pytest.raises(IntegrityError, match="uq_clinic_memberships_clinic_id_user_id"):
            staff.memberships.add(a_membership(clinic.id, user.id, Role.FRONT_DESK))


def test_one_user_can_hold_memberships_in_two_clinics(uow_factory: UowFactory) -> None:
    clinic_a, clinic_b, user = a_clinic(), a_clinic(), a_user()
    with uow_factory() as uow:
        uow.clinics.add(clinic_a)
        uow.clinics.add(clinic_b)
        uow.users.add(user)
        uow.tenant(clinic_a.id).memberships.add(a_membership(clinic_a.id, user.id, Role.DOCTOR))
        uow.tenant(clinic_b.id).memberships.add(a_membership(clinic_b.id, user.id, Role.OWNER))
        uow.commit()


def test_one_doctor_profile_per_user_per_clinic(uow_factory: UowFactory) -> None:
    clinic, user = a_clinic(), a_user()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(user)
        doctors = uow.tenant(clinic.id).doctors
        doctors.add(a_doctor(clinic.id))  # doctors without a user are unlimited
        doctors.add(a_doctor(clinic.id))
        doctors.add(a_doctor(clinic.id, user_id=user.id))
        with pytest.raises(IntegrityError, match="uq_doctors_clinic_id_user_id"):
            doctors.add(a_doctor(clinic.id, user_id=user.id))


@pytest.mark.parametrize(
    ("make_duplicate", "constraint"),
    [
        (lambda u: a_user(email=u.email, phone=None), "uq_users_email"),
        (lambda u: a_user(email=None, phone=u.phone), "uq_users_phone_e164"),
    ],
)
def test_email_and_phone_identify_one_user(
    uow_factory: UowFactory, make_duplicate: object, constraint: str
) -> None:
    user = a_user()
    with uow_factory() as uow:
        uow.users.add(user)
        with pytest.raises(IntegrityError, match=constraint):
            uow.users.add(make_duplicate(user))  # type: ignore[operator]


def test_slug_is_unique(uow_factory: UowFactory) -> None:
    with uow_factory() as uow:
        uow.clinics.add(a_clinic(slug="sample-clinic"))
        with pytest.raises(IntegrityError, match="uq_clinics_slug"):
            uow.clinics.add(a_clinic(slug="sample-clinic"))


@pytest.mark.parametrize(
    ("statement", "constraint"),
    [
        (
            "INSERT INTO users (id, full_name, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'X', 'ACTIVE', now(), now())",
            "ck_users_email_or_phone",
        ),
        (
            "INSERT INTO users (id, full_name, email, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'X', 'Upper@example.test', 'ACTIVE', now(), now())",
            "ck_users_email_lower_case",
        ),
        (
            "INSERT INTO users (id, full_name, email, status, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'X', 'x@example.test', 'LOCKED', now(), now())",
            "ck_users_status",
        ),
        (
            "INSERT INTO clinics (id, name, slug, status, patient_code_prefix, created_at, "
            "updated_at) VALUES (gen_random_uuid(), 'X', 'x-clinic', 'CLOSED', 'XX', now(), now())",
            "ck_clinics_status",
        ),
        (
            "INSERT INTO clinics (id, name, slug, status, patient_code_prefix, created_at, "
            "updated_at) VALUES (gen_random_uuid(), 'X', 'x-clinic', 'ACTIVE', 'x', now(), now())",
            "ck_clinics_patient_code_prefix_format",
        ),
        (
            "INSERT INTO clinics (id, name, slug, status, patient_code_prefix, next_patient_seq, "
            "created_at, updated_at) VALUES (gen_random_uuid(), 'X', 'x-clinic', 'ACTIVE', 'XX', "
            "0, now(), now())",
            "ck_clinics_next_patient_seq_positive",
        ),
    ],
)
def test_database_rejects_rows_the_domain_would_never_build(
    uow_factory: UowFactory, statement: str, constraint: str
) -> None:
    # Defence in depth: a script or a future bug that bypasses the domain still
    # cannot store an invalid row.

    with uow_factory() as uow:
        session = uow._require_open().session
        with pytest.raises(IntegrityError, match=constraint):
            session.execute(text(statement))


def test_membership_role_and_status_checks(uow_factory: UowFactory) -> None:

    clinic, user = a_clinic(), a_user()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(user)
        session = uow._require_open().session
        with pytest.raises(IntegrityError, match="ck_clinic_memberships_role"):
            session.execute(
                text(
                    "INSERT INTO clinic_memberships "
                    "(id, clinic_id, user_id, role, status, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :c, :u, 'ADMIN', 'ACTIVE', now(), now())"
                ),
                {"c": clinic.id, "u": user.id},
            )
