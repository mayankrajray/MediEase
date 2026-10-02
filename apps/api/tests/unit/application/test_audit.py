"""Audit events written by the session use cases (FR-AUD-01; spec R11).

The role change that proves AC5 is tested end to end over HTTP
(``tests/integration/test_audit_http.py``), where a real transaction and the
append-only table are involved.
"""

from __future__ import annotations

import pytest

from mediease_api.application.auth.errors import AccountDisabled, InvalidCredentials
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType
from mediease_api.domain.identity.user import User
from tests.unit.application.harness import PASSWORD, Auth, build_auth
from tests.unit.application.harness import cmd as _cmd


def _email(user: User) -> str:
    assert user.email is not None
    return user.email.value


def test_fr_aud_01_a_successful_sign_in_is_recorded_once(auth: Auth) -> None:
    user = auth.add_user(clinics=2)
    auth.session_of(user)

    events = auth.events()
    assert [e.action for e in events] == [AuditAction.AUTH_SIGNED_IN]
    event = events[0]
    assert event.actor_type is ActorType.STAFF
    assert event.actor_user_id == user.id
    assert event.clinic_id is None  # a sign-in belongs to a user, not a clinic
    assert event.request_id == auth.info.request_id
    assert event.ip_hash == auth.info.ip_hash
    assert set(event.metadata) == {"session_id", "clinic_count"}
    assert event.metadata["clinic_count"] == "2"
    assert event.occurred_at == auth.clock.now()


def test_an_ops_sign_in_is_recorded_as_an_ops_actor(auth: Auth) -> None:
    user = auth.add_user(clinics=0, is_platform_ops=True)
    auth.session_of(user)
    assert auth.events()[0].actor_type is ActorType.OPS


def test_fr_aud_01_a_wrong_password_is_recorded_with_its_reason(auth: Auth) -> None:
    user = auth.add_user()
    with pytest.raises(InvalidCredentials):
        auth.sign_in.execute(_cmd(_email(user), "wrong"), auth.info)

    events = auth.events()
    assert [(e.action, e.metadata["reason"]) for e in events] == [
        (AuditAction.AUTH_SIGN_IN_FAILED, "wrong_password")
    ]
    assert events[0].metadata["locked"] == "false"
    assert PASSWORD not in str(events) and _email(user) not in str(events)


def test_the_failure_that_locks_the_account_says_so(auth: Auth) -> None:
    user = auth.add_user()
    for _ in range(5):
        with pytest.raises(InvalidCredentials):
            auth.sign_in.execute(_cmd(_email(user), "wrong"), auth.info)

    locked = [e for e in auth.events() if e.metadata.get("locked") == "true"]
    assert len(locked) == 1
    # The five attempts are recorded; attempts made while locked are not, so a
    # caller cannot grow the table by retrying.
    assert len(auth.events()) == 5
    with pytest.raises(Exception, match="Too many attempts"):
        auth.sign_in.execute(_cmd(_email(user)), auth.info)
    assert len(auth.events()) == 5


@pytest.mark.parametrize(
    ("identifier", "password"),
    [("nobody@example.test", PASSWORD), ("not an id", PASSWORD)],
    ids=["unknown-identifier", "unparseable"],
)
def test_unknown_identifiers_are_not_recorded(auth: Auth, identifier: str, password: str) -> None:
    auth.add_user()
    with pytest.raises(InvalidCredentials):
        auth.sign_in.execute(_cmd(identifier, password), auth.info)
    assert auth.events() == []


def test_a_user_without_a_password_is_not_recorded(auth: Auth) -> None:
    user = auth.add_user()
    auth.uow.committed.users[user.id].password_hash = None
    with pytest.raises(InvalidCredentials):
        auth.sign_in.execute(_cmd(_email(user)), auth.info)
    assert auth.events() == []


def test_a_disabled_account_with_the_right_password_is_recorded(auth: Auth) -> None:
    user = auth.add_user()
    auth.stored(user).disable(now=auth.clock.now())
    with pytest.raises(AccountDisabled):
        auth.sign_in.execute(_cmd(_email(user)), auth.info)

    assert [(e.action, e.metadata["reason"]) for e in auth.events()] == [
        (AuditAction.AUTH_SIGN_IN_FAILED, "disabled")
    ]


def test_a_user_without_an_active_membership_is_recorded(auth: Auth) -> None:
    user = auth.add_user(clinics=0)
    with pytest.raises(AccountDisabled):
        auth.sign_in.execute(_cmd(_email(user)), auth.info)
    assert auth.events()[0].metadata["reason"] == "no_active_membership"


def test_fr_aud_01_signing_out_is_recorded_with_the_session(auth: Auth) -> None:
    user = auth.add_user()
    tokens = auth.session_of(user).tokens
    auth.sign_out.execute(tokens.refresh_token, auth.info)

    signed_out = auth.events()[-1]
    assert signed_out.action is AuditAction.AUTH_SIGNED_OUT
    assert signed_out.actor_user_id == user.id
    assert signed_out.metadata["revoked_count"] == "1"
    assert signed_out.metadata["session_id"] == auth.events()[0].metadata["session_id"]


def test_sign_out_without_a_live_session_records_nothing(auth: Auth) -> None:
    auth.add_user()
    auth.sign_out.execute("refresh-unknown", auth.info)
    auth.sign_out.execute(None, auth.info)
    assert auth.events() == []


def test_fr_aud_01_a_replayed_refresh_token_is_recorded(auth: Auth) -> None:
    user = auth.add_user()
    first = auth.session_of(user).tokens.refresh_token
    auth.refresh.execute(first, auth.info)

    with pytest.raises(Exception, match="this session was ended"):
        auth.refresh.execute(first, auth.info)

    reused = auth.events()[-1]
    assert reused.action is AuditAction.AUTH_REFRESH_REUSED
    assert reused.actor_user_id == user.id
    assert int(reused.metadata["revoked_count"]) >= 1


def test_a_successful_refresh_is_not_recorded(auth: Auth) -> None:
    """Rotation is routine: the sign-in and the sign-out bound the session."""
    user = auth.add_user()
    token = auth.session_of(user).tokens.refresh_token
    auth.refresh.execute(token, auth.info)
    assert [e.action for e in auth.events()] == [AuditAction.AUTH_SIGNED_IN]


def test_r11_a_failed_audit_write_stops_the_change() -> None:
    """An unaudited change must not commit: no session, no sign-in state."""
    auth = build_auth(audit_fails=True)
    user = auth.add_user()

    with pytest.raises(RuntimeError, match=r"auth\.signed_in"):
        auth.session_of(user)

    assert auth.uow.commits == 0
    assert auth.uow.committed.refresh_tokens == {}
    assert auth.stored(user).last_signed_in_at is None
    assert auth.events() == []
