"""Patient accounts and external identities (M6a-P3, ADR-0015 decisions 1, 4, 5)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from mediease_api.domain.identity.external import ExternalIdentity, IdentityProvider
from mediease_api.domain.portal.account import (
    AccountStatus,
    PatientAccount,
    SignInMethod,
)
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, new_id

EMAIL = EmailAddress.parse("asha.patient@example.test")


def _password_account() -> PatientAccount:
    return PatientAccount.with_password(
        id=new_id(), full_name="  Asha Patient ", email=EMAIL, password_hash="hash", now=NOW
    )


def test_fr_prt_01_a_password_account_starts_active_and_unverified() -> None:
    account = _password_account()
    assert account.full_name == "Asha Patient"
    assert account.sign_in_method is SignInMethod.PASSWORD
    assert account.status is AccountStatus.ACTIVE
    assert not account.is_email_verified
    assert "hash" not in repr(account)


def test_fr_prt_01_a_google_account_is_verified_and_has_no_password() -> None:
    account = PatientAccount.from_google(id=new_id(), full_name="Asha", email=EMAIL, now=NOW)
    assert account.sign_in_method is SignInMethod.GOOGLE
    assert account.email_verified_at == NOW
    assert account.password_hash is None
    with pytest.raises(InvalidValue):
        account.set_password_hash("x", now=NOW)


def test_fr_auth_04_five_wrong_passwords_lock_a_patient_for_15_minutes() -> None:
    account = _password_account()
    locked = [account.record_failed_sign_in(now=NOW) for _ in range(5)]
    assert locked == [False, False, False, False, True]
    assert account.is_locked(NOW + timedelta(minutes=14))
    assert not account.is_locked(NOW + timedelta(minutes=15))
    account.record_successful_sign_in(now=NOW + timedelta(minutes=16))
    assert account.failed_sign_in_count == 0
    assert account.locked_until is None


def test_a_password_account_needs_a_hash_and_a_name() -> None:
    with pytest.raises(InvalidValue):
        PatientAccount.with_password(
            id=new_id(), full_name="Asha", email=EMAIL, password_hash="", now=NOW
        )
    with pytest.raises(InvalidValue):
        PatientAccount.with_password(
            id=new_id(), full_name="  ", email=EMAIL, password_hash="h", now=NOW
        )


def test_adr_0015_an_identity_belongs_to_exactly_one_kind_of_account() -> None:
    staff = ExternalIdentity.for_staff(
        id=new_id(), provider=IdentityProvider.GOOGLE, subject="sub-1", user_id=new_id(), now=NOW
    )
    assert staff.patient_account_id is None
    with pytest.raises(InvalidValue):
        ExternalIdentity(new_id(), IdentityProvider.GOOGLE, "sub-1", new_id(), new_id(), NOW, NOW)
    with pytest.raises(InvalidValue):
        ExternalIdentity(new_id(), IdentityProvider.GOOGLE, "sub-1", None, None, NOW, NOW)
    with pytest.raises(InvalidValue):
        ExternalIdentity.for_patient(
            id=new_id(),
            provider=IdentityProvider.GOOGLE,
            subject="",
            patient_account_id=new_id(),
            now=NOW,
        )
    later = NOW + timedelta(days=1)
    staff.record_use(now=later)
    assert staff.last_used_at == later
