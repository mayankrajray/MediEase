"""Credentials, lockout and refresh-token states (FR-AUTH-02, FR-AUTH-04; spec R3, R5)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from mediease_api.domain.identity.session import RefreshToken, RefreshTokenState
from mediease_api.domain.identity.user import LOCKOUT_DURATION, MAX_FAILED_SIGN_INS
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from tests.builders import NOW, a_user, new_id

# --- Lockout ---------------------------------------------------------------------------------


def test_fr_auth_04_fifth_consecutive_failure_locks_for_15_minutes() -> None:
    user = a_user()
    for attempt in range(1, MAX_FAILED_SIGN_INS):
        assert user.record_failed_sign_in(now=NOW) is False
        assert user.failed_sign_in_count == attempt
        assert not user.is_locked(NOW)

    assert user.record_failed_sign_in(now=NOW) is True
    assert user.locked_until == NOW + LOCKOUT_DURATION == NOW + timedelta(minutes=15)
    assert user.is_locked(NOW + timedelta(minutes=14, seconds=59))
    assert not user.is_locked(NOW + timedelta(minutes=15))


def test_fr_auth_04_lock_resets_the_count_so_expiry_gives_fresh_attempts() -> None:
    user = a_user()
    for _ in range(MAX_FAILED_SIGN_INS):
        user.record_failed_sign_in(now=NOW)
    assert user.failed_sign_in_count == 0

    after = NOW + LOCKOUT_DURATION
    assert user.record_failed_sign_in(now=after) is False
    assert not user.is_locked(after)


def test_r3_success_resets_count_and_records_time() -> None:
    user = a_user()
    user.record_failed_sign_in(now=NOW)
    user.record_failed_sign_in(now=NOW)
    later = NOW + timedelta(minutes=1)
    user.record_successful_sign_in(now=later)
    assert user.failed_sign_in_count == 0
    assert user.locked_until is None
    assert user.last_signed_in_at == later
    assert user.updated_at == later


def test_password_hash_is_set_and_hidden_from_repr() -> None:
    user = a_user()
    assert user.password_hash is None
    user.set_password_hash("$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA", now=NOW)
    assert user.password_hash is not None
    assert "argon2" not in repr(user)
    with pytest.raises(InvalidValue):
        user.set_password_hash("", now=NOW)


def test_is_active_follows_status() -> None:
    user = a_user()
    assert user.is_active
    user.disable(now=NOW)
    assert not user.is_active


# --- Refresh tokens ----------------------------------------------------------------------------


def _token(ttl: timedelta = timedelta(days=14)) -> RefreshToken:
    return RefreshToken.issue(
        id=new_id(), user_id=new_id(), family_id=new_id(), token_hash="h" * 64, now=NOW, ttl=ttl
    )


def test_fr_auth_02_new_token_is_active_until_it_expires() -> None:
    token = _token(ttl=timedelta(days=14))
    assert token.expires_at == NOW + timedelta(days=14)
    assert token.state(NOW) is RefreshTokenState.ACTIVE
    assert token.state(NOW + timedelta(days=14)) is RefreshTokenState.EXPIRED
    assert "h" * 64 not in repr(token)


def test_r5_rotation_marks_the_token_replaced() -> None:
    token = _token()
    successor = new_id()
    token.mark_replaced(successor, now=NOW)
    assert token.replaced_by_id == successor
    assert token.revoked_at == NOW
    assert token.state(NOW) is RefreshTokenState.ROTATED


def test_r5_a_rotated_token_is_recognised_even_after_family_revocation() -> None:
    token = _token()
    token.mark_replaced(new_id(), now=NOW)
    # A later family-wide revocation leaves replaced_by_id in place: still reuse.
    assert token.state(NOW + timedelta(days=30)) is RefreshTokenState.ROTATED


def test_revoked_token_state() -> None:
    token = _token()
    token.revoked_at = NOW
    assert token.state(NOW) is RefreshTokenState.REVOKED


@pytest.mark.parametrize("make_unusable", ["rotated", "expired"])
def test_only_an_active_token_can_rotate(make_unusable: str) -> None:
    token = _token(ttl=timedelta(seconds=1))
    when = NOW
    if make_unusable == "rotated":
        token.mark_replaced(new_id(), now=NOW)
    else:
        when = NOW + timedelta(seconds=1)
    with pytest.raises(InvalidTransition):
        token.mark_replaced(new_id(), now=when)
