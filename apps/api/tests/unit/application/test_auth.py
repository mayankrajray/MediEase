"""Sign-in, refresh and sign-out use cases with in-memory fakes (FR-AUTH-01/02/04; R1-R5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pytest

from mediease_api.application.auth._session import SessionIssuer
from mediease_api.application.auth.errors import (
    AccountDisabled,
    AccountLocked,
    InvalidCredentials,
    RefreshTokenReused,
    SessionExpired,
)
from mediease_api.application.auth.refresh_session import RefreshSession
from mediease_api.application.auth.sign_in import SignIn, SignInCommand
from mediease_api.application.auth.sign_out import SignOut
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.access import ClinicAccess
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.session import RefreshTokenState
from mediease_api.domain.identity.user import User
from tests.builders import a_user, new_id
from tests.conftest import LogReader
from tests.fakes import (
    FakeAccessTokens,
    FakeClock,
    FakeHasher,
    FakeIds,
    FakeRefreshSecrets,
    InMemoryUnitOfWork,
)

PASSWORD = "correct horse battery"
REFRESH_TTL = timedelta(days=14)


@dataclass
class Auth:
    uow: InMemoryUnitOfWork
    clock: FakeClock
    hasher: FakeHasher
    secrets: FakeRefreshSecrets
    sign_in: SignIn
    refresh: RefreshSession
    sign_out: SignOut

    def add_user(self, *, clinics: int = 1, **overrides: object) -> User:
        user = a_user(password_hash=self.hasher.hash(PASSWORD), **overrides)
        self.uow.committed.users[user.id] = user
        self.uow.committed.access[user.id] = [
            ClinicAccess(
                membership_id=new_id(),
                clinic_id=new_id(),
                clinic_name=f"Sample Clinic {i}",
                clinic_status=ClinicStatus.ACTIVE,
                role=Role.OWNER,
            )
            for i in range(clinics)
        ]
        return user

    def stored(self, user: User) -> User:
        return self.uow.committed.users[user.id]


@pytest.fixture
def auth() -> Auth:
    uow, clock, hasher, secrets = (
        InMemoryUnitOfWork(),
        FakeClock(),
        FakeHasher(),
        FakeRefreshSecrets(),
    )
    ids = FakeIds()
    sessions = SessionIssuer(
        ids=ids, secrets=secrets, access_tokens=FakeAccessTokens(), refresh_ttl=REFRESH_TTL
    )
    return Auth(
        uow=uow,
        clock=clock,
        hasher=hasher,
        secrets=secrets,
        sign_in=SignIn(
            uow=uow,
            clock=clock,
            ids=ids,
            hasher=hasher,
            sessions=sessions,
            dummy_password_hash=hasher.hash("dummy-password-never-used"),
        ),
        refresh=RefreshSession(uow=uow, clock=clock, secrets=secrets, sessions=sessions),
        sign_out=SignOut(uow=uow, clock=clock, secrets=secrets),
    )


def _cmd(identifier: str, password: str = PASSWORD) -> SignInCommand:
    return SignInCommand(identifier=identifier, password=password)


# --- Sign-in ---------------------------------------------------------------------------------


def test_fr_auth_01_sign_in_with_email_returns_user_memberships_and_tokens(auth: Auth) -> None:
    user = auth.add_user(clinics=2)
    assert user.email is not None
    result = auth.sign_in.execute(_cmd(f"  {user.email.value.upper()} "))

    assert result.user.id == user.id
    assert [m.clinic_name for m in result.memberships] == ["Sample Clinic 0", "Sample Clinic 1"]
    assert result.tokens.refresh_expires_at == auth.clock.now() + REFRESH_TTL
    stored_tokens = list(auth.uow.committed.refresh_tokens.values())
    assert len(stored_tokens) == 1
    assert stored_tokens[0].token_hash == auth.secrets.digest(result.tokens.refresh_token)
    assert result.tokens.refresh_token not in repr(result)
    assert auth.stored(user).last_signed_in_at == auth.clock.now()


def test_r1_sign_in_with_phone_in_any_indian_format(auth: Auth) -> None:
    user = auth.add_user()
    assert user.phone is not None
    national = user.phone.e164[3:]
    result = auth.sign_in.execute(_cmd(f"0{national[:5]} {national[5:]}"))
    assert result.user.id == user.id


@pytest.mark.parametrize("identifier", ["nobody@example.test", "9000099999", "not an id", ""])
def test_r2_unknown_identifier_is_invalid_credentials_and_still_hashes(
    auth: Auth, identifier: str
) -> None:
    auth.add_user()
    with pytest.raises(InvalidCredentials) as excinfo:
        auth.sign_in.execute(_cmd(identifier))
    assert excinfo.value.code == "AUTH_INVALID_CREDENTIALS"
    assert auth.hasher.verifications == 1  # constant-time path: one verification either way
    assert auth.uow.commits == 0


def test_r2_wrong_password_gives_the_same_error_as_unknown_user(auth: Auth) -> None:
    user = auth.add_user()
    assert user.email is not None
    with pytest.raises(InvalidCredentials) as wrong:
        auth.sign_in.execute(_cmd(user.email.value, "wrong"))
    with pytest.raises(InvalidCredentials) as unknown:
        auth.sign_in.execute(_cmd("nobody@example.test", "wrong"))
    assert wrong.value.message == unknown.value.message
    assert wrong.value.details == unknown.value.details == {}


def test_user_without_a_password_cannot_sign_in(auth: Auth) -> None:
    user = auth.add_user()
    auth.uow.committed.users[user.id].password_hash = None
    assert user.email is not None
    with pytest.raises(InvalidCredentials):
        auth.sign_in.execute(_cmd(user.email.value))
    assert auth.hasher.verifications == 1


def test_ac1_fr_auth_04_sixth_attempt_with_correct_password_is_locked(auth: Auth) -> None:
    user = auth.add_user()
    assert user.email is not None
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            auth.sign_in.execute(_cmd(user.email.value, "wrong"))
    assert auth.stored(user).locked_until == auth.clock.now() + timedelta(minutes=15)

    auth.clock.advance(minutes=14)
    with pytest.raises(AccountLocked) as excinfo:
        auth.sign_in.execute(_cmd(user.email.value))  # the correct password
    assert excinfo.value.code == "AUTH_LOCKED"
    assert excinfo.value.retry_after_seconds == 60
    assert not auth.uow.committed.refresh_tokens


def test_r3_lock_expires_after_15_minutes_and_success_resets_the_count(auth: Auth) -> None:
    user = auth.add_user()
    assert user.email is not None
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            auth.sign_in.execute(_cmd(user.email.value, "wrong"))
    auth.clock.advance(minutes=15)
    auth.sign_in.execute(_cmd(user.email.value))
    stored = auth.stored(user)
    assert stored.failed_sign_in_count == 0 and stored.locked_until is None


def test_r3_failures_are_committed_and_a_success_in_between_resets_them(auth: Auth) -> None:
    user = auth.add_user()
    assert user.email is not None
    for _ in range(4):
        with pytest.raises(InvalidCredentials):
            auth.sign_in.execute(_cmd(user.email.value, "wrong"))
    assert auth.stored(user).failed_sign_in_count == 4
    auth.sign_in.execute(_cmd(user.email.value))
    with pytest.raises(InvalidCredentials):
        auth.sign_in.execute(_cmd(user.email.value, "wrong"))
    assert auth.stored(user).locked_until is None


def test_locking_failure_logs_auth_locked_without_the_identifier(
    auth: Auth, json_logs: LogReader
) -> None:
    user = auth.add_user()
    assert user.email is not None
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            auth.sign_in.execute(_cmd(user.email.value, "Typo-Secret-42"))
    logs = json_logs()
    events = [e["event"] for e in logs]
    assert events.count("auth.sign_in_failed") == 5
    assert events[-1] == "auth.locked"
    assert user.email.value not in str(logs)
    assert "Typo-Secret-42" not in str(logs)


def test_r7_disabled_user_with_right_password_is_account_disabled(auth: Auth) -> None:
    user = auth.add_user()
    auth.stored(user).disable(now=auth.clock.now())
    assert user.email is not None
    with pytest.raises(AccountDisabled) as excinfo:
        auth.sign_in.execute(_cmd(user.email.value))
    assert excinfo.value.code == "AUTH_ACCOUNT_DISABLED"
    # ... and with a wrong password it does not reveal the status.
    with pytest.raises(InvalidCredentials):
        auth.sign_in.execute(_cmd(user.email.value, "wrong"))


def test_user_without_an_active_membership_is_account_disabled(auth: Auth) -> None:
    user = auth.add_user(clinics=0)
    assert user.email is not None
    with pytest.raises(AccountDisabled):
        auth.sign_in.execute(_cmd(user.email.value))
    assert not auth.uow.committed.refresh_tokens


def test_r10_platform_ops_user_signs_in_without_a_membership(auth: Auth) -> None:
    user = auth.add_user(clinics=0, is_platform_ops=True)
    assert user.email is not None
    result = auth.sign_in.execute(_cmd(user.email.value))
    assert result.user.is_platform_ops and result.memberships == ()


def test_outdated_hash_is_upgraded_on_successful_sign_in(auth: Auth) -> None:
    user = auth.add_user()
    old_hash = auth.stored(user).password_hash
    assert old_hash is not None and user.email is not None
    auth.hasher.outdated.add(old_hash)
    auth.uow.committed.users[user.id].password_hash = old_hash
    auth.sign_in.execute(_cmd(user.email.value))
    assert auth.stored(user).password_hash == auth.hasher.hash(PASSWORD)
    assert auth.stored(user).updated_at == auth.clock.now()


def test_sign_in_command_hides_the_password() -> None:
    assert PASSWORD not in repr(_cmd("owner@example.test"))


# --- Refresh ---------------------------------------------------------------------------------


def _signed_in(auth: Auth) -> tuple[User, str]:
    user = auth.add_user()
    assert user.email is not None
    return user, auth.sign_in.execute(_cmd(user.email.value)).tokens.refresh_token


def test_fr_auth_02_refresh_rotates_within_the_family(auth: Auth) -> None:
    user, first = _signed_in(auth)
    auth.clock.advance(minutes=20)
    result = auth.refresh.execute(first)

    assert result.user.id == user.id
    assert result.tokens.refresh_token != first
    tokens = {t.token_hash: t for t in auth.uow.committed.refresh_tokens.values()}
    old = tokens[auth.secrets.digest(first)]
    new = tokens[auth.secrets.digest(result.tokens.refresh_token)]
    assert old.family_id == new.family_id
    assert old.replaced_by_id == new.id
    assert old.state(auth.clock.now()) is RefreshTokenState.ROTATED
    assert new.state(auth.clock.now()) is RefreshTokenState.ACTIVE
    # Sliding expiry: the successor gets a fresh 14 days.
    assert new.expires_at == auth.clock.now() + REFRESH_TTL


def test_ac2_r5_reusing_a_rotated_token_revokes_the_whole_family(
    auth: Auth, json_logs: LogReader
) -> None:
    _, first = _signed_in(auth)
    second = auth.refresh.execute(first).tokens.refresh_token

    with pytest.raises(RefreshTokenReused) as excinfo:
        auth.refresh.execute(first)
    assert excinfo.value.code == "AUTH_REFRESH_REUSED"
    assert any(e["event"] == "auth.refresh_reused" and e["level"] == "warning" for e in json_logs())

    # The newer token in the family stopped working too.
    with pytest.raises(SessionExpired):
        auth.refresh.execute(second)
    assert all(t.revoked_at for t in auth.uow.committed.refresh_tokens.values())


def test_reuse_revocation_leaves_other_sessions_alone(auth: Auth) -> None:
    user, first = _signed_in(auth)
    assert user.email is not None
    other = auth.sign_in.execute(_cmd(user.email.value)).tokens.refresh_token
    auth.refresh.execute(first)
    with pytest.raises(RefreshTokenReused):
        auth.refresh.execute(first)
    auth.refresh.execute(other)  # a separate sign-in is a separate family


@pytest.mark.parametrize("token", ["refresh-999", "", "garbage"])
def test_unknown_refresh_token_is_session_expired(auth: Auth, token: str) -> None:
    _signed_in(auth)
    with pytest.raises(SessionExpired) as excinfo:
        auth.refresh.execute(token)
    assert excinfo.value.code == "AUTH_SESSION_EXPIRED"


def test_expired_refresh_token_is_session_expired(auth: Auth) -> None:
    _, token = _signed_in(auth)
    auth.clock.advance(days=14)
    with pytest.raises(SessionExpired):
        auth.refresh.execute(token)


def test_r7_disabled_user_loses_the_session_on_refresh(auth: Auth) -> None:
    user, token = _signed_in(auth)
    auth.stored(user).disable(now=auth.clock.now())
    with pytest.raises(AccountDisabled):
        auth.refresh.execute(token)
    assert all(t.revoked_at for t in auth.uow.committed.refresh_tokens.values())


def test_r7_losing_the_last_membership_ends_the_session_on_refresh(auth: Auth) -> None:
    user, token = _signed_in(auth)
    auth.uow.committed.access[user.id] = []
    with pytest.raises(AccountDisabled):
        auth.refresh.execute(token)


# --- Sign-out ---------------------------------------------------------------------------------


def test_fr_auth_02_sign_out_revokes_the_family(auth: Auth, json_logs: LogReader) -> None:
    _, first = _signed_in(auth)
    second = auth.refresh.execute(first).tokens.refresh_token
    json_logs()  # discard sign-in and refresh events
    auth.sign_out.execute(second)
    assert any(e["event"] == "auth.signed_out" for e in json_logs())
    with pytest.raises(SessionExpired):
        auth.refresh.execute(second)


@pytest.mark.parametrize("token", [None, "", "refresh-unknown"])
def test_sign_out_is_idempotent(auth: Auth, token: str | None) -> None:
    _signed_in(auth)
    auth.sign_out.execute(token)
    assert auth.uow.commits == 1  # only the sign-in committed


def test_sign_out_twice_is_harmless(auth: Auth) -> None:
    _, token = _signed_in(auth)
    auth.sign_out.execute(token)
    auth.sign_out.execute(token)
