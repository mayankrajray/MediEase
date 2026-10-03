"""``make seed`` against a real migrated database (local demo data only)."""

from __future__ import annotations

import pytest

from mediease_api.adapters.security.argon2_hasher import Argon2PasswordHasher
from mediease_api.delivery.cli import seed
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.shared.email import EmailAddress
from tests.conftest import TEST_IP_SALT, TEST_SIGNING_KEY, SetEnv, UowFactory


@pytest.fixture
def seed_env(set_env: SetEnv, migrated_database_url: str) -> dict[str, str]:
    env = {
        "APP_ENV": "local",
        "DATABASE_URL": migrated_database_url,
        "JWT_SIGNING_KEY": TEST_SIGNING_KEY,
        "AUDIT_IP_SALT": TEST_IP_SALT,
    }
    set_env(env)
    return env


def test_seed_creates_an_active_clinic_with_three_roles_and_an_ops_user(
    seed_env: dict[str, str], uow_factory: UowFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    assert seed.main(["--password", "local-demo-password"]) == 0
    assert "created 'sample-clinic'" in capsys.readouterr().out

    with uow_factory() as uow:
        clinic = uow.clinics.get_by_slug(seed.DEMO_SLUG)
        assert clinic is not None and clinic.status is ClinicStatus.ACTIVE
        staff = uow.tenant(clinic.id)
        assert sorted(m.role for m in staff.memberships.list()) == sorted(
            [Role.OWNER, Role.DOCTOR, Role.FRONT_DESK]
        )
        assert len(staff.doctors.list()) == 1

        ops = uow.users.get_by_email(EmailAddress.parse("ops@mediease.example"))
        assert ops is not None and ops.is_platform_ops
        assert ops.password_hash is not None
        assert Argon2PasswordHasher().verify(ops.password_hash, "local-demo-password")


def test_seed_is_idempotent(
    seed_env: dict[str, str], uow_factory: UowFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    assert seed.main([]) == 0
    assert seed.main([]) == 0
    out = capsys.readouterr().out
    assert "'sample-clinic' already exists" in out
    assert "'sample-clinic-two' already exists" in out


def test_seed_creates_a_second_clinic_sharing_the_doctor_so_the_switcher_can_be_tried(
    seed_env: dict[str, str], uow_factory: UowFactory
) -> None:
    assert seed.main([]) == 0

    with uow_factory() as uow:
        doctor = uow.users.get_by_email(EmailAddress.parse("doctor@sample-clinic.example"))
        assert doctor is not None
        access = uow.clinic_access.list_active_for_user(doctor.id)
        assert sorted(a.clinic_name for a in access) == ["Sample Clinic", "Sample Clinic Two"]

        second = uow.clinics.get_by_slug(seed.SECOND_SLUG)
        assert second is not None and second.status is ClinicStatus.ACTIVE
        staff = uow.tenant(second.id)
        assert sorted(m.role for m in staff.memberships.list()) == sorted([Role.OWNER, Role.DOCTOR])
        assert len(staff.doctors.list()) == 1

        owner = uow.users.get_by_email(EmailAddress.parse("owner@sample-clinic.example"))
        assert owner is not None and len(uow.clinic_access.list_active_for_user(owner.id)) == 1


def test_seed_adds_only_the_missing_clinic_to_a_database_seeded_before_clinic_two(
    seed_env: dict[str, str],
    uow_factory: UowFactory,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A local database seeded by the previous version: the first clinic only.
    both = seed._CLINICS
    monkeypatch.setattr(seed, "_CLINICS", both[:1])
    assert seed.main([]) == 0
    monkeypatch.setattr(seed, "_CLINICS", both)
    capsys.readouterr()

    assert seed.main([]) == 0

    out = capsys.readouterr().out
    assert "'sample-clinic' already exists" in out
    assert "created 'sample-clinic-two'" in out
    with uow_factory() as uow:
        doctor = uow.users.get_by_email(EmailAddress.parse("doctor@sample-clinic.example"))
        assert doctor is not None
        assert len(uow.clinic_access.list_active_for_user(doctor.id)) == 2
        first = uow.clinics.get_by_slug(seed.DEMO_SLUG)
        assert first is not None
        assert len(uow.tenant(first.id).memberships.list()) == 3  # untouched, not duplicated


def test_seed_refuses_outside_local(
    seed_env: dict[str, str], set_env: SetEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    set_env({**seed_env, "APP_ENV": "test", "DATABASE_URL": "postgresql+psycopg://u:p@h/db"})
    assert seed.main([]) == 2
    assert "refused" in capsys.readouterr().err
