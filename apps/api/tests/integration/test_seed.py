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
    assert "already exists" in capsys.readouterr().out


def test_seed_refuses_outside_local(
    seed_env: dict[str, str], set_env: SetEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    set_env({**seed_env, "APP_ENV": "test", "DATABASE_URL": "postgresql+psycopg://u:p@h/db"})
    assert seed.main([]) == 2
    assert "refused" in capsys.readouterr().err
