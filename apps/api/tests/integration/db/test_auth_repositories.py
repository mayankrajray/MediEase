"""Credentials, refresh tokens and clinic access against real PostgreSQL (M1-P2).

Proves the sign-in state round-trips, refresh tokens rotate and revoke by
family, row locks really serialise concurrent sign-ins, and the cross-clinic
access read returns only active memberships.
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.session import RefreshToken, RefreshTokenState
from mediease_api.domain.shared.errors import NotFound
from tests.builders import LATER, NOW, a_clinic, a_membership, a_user, new_id
from tests.conftest import UowFactory


def _token(user_id: UUID, family_id: UUID | None = None, digest: str | None = None) -> RefreshToken:
    return RefreshToken.issue(
        id=new_id(),
        user_id=user_id,
        family_id=family_id or new_id(),
        token_hash=digest or new_id().hex * 2,
        now=NOW,
        ttl=timedelta(days=14),
    )


def test_fr_auth_04_lockout_state_round_trips(uow_factory: UowFactory) -> None:
    user = a_user(password_hash="$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaA")
    with uow_factory() as uow:
        uow.users.add(user)
        uow.commit()

    for _ in range(5):
        user.record_failed_sign_in(now=NOW)
    with uow_factory() as uow:
        uow.users.update(user)
        uow.commit()

    with uow_factory() as uow:
        assert user.email is not None
        stored = uow.users.get_by_email(user.email, for_update=True)
        assert stored is not None
        assert stored.password_hash == user.password_hash
        assert stored.locked_until == NOW + timedelta(minutes=15)
        assert stored.is_locked(NOW)
        stored.record_successful_sign_in(now=LATER)
        uow.users.update(stored)
        uow.commit()

    with uow_factory() as uow:
        assert user.phone is not None
        stored = uow.users.get_by_phone(user.phone, for_update=True)
        assert stored is not None
        assert stored.last_signed_in_at == LATER
        assert stored.failed_sign_in_count == 0 and stored.locked_until is None


def test_for_update_serialises_concurrent_sign_ins(uow_factory: UowFactory) -> None:
    """A second transaction waits for the first's lock, then sees its committed count."""
    user = a_user()
    with uow_factory() as uow:
        uow.users.add(user)
        uow.commit()
    assert user.email is not None
    email = user.email
    seen: list[int] = []

    def second_attempt() -> None:
        with uow_factory() as uow:
            locked = uow.users.get_by_email(email, for_update=True)
            assert locked is not None
            seen.append(locked.failed_sign_in_count)

    with uow_factory() as uow:
        first = uow.users.get_by_email(email, for_update=True)
        assert first is not None
        waiter = threading.Thread(target=second_attempt)
        waiter.start()
        time.sleep(0.3)
        assert seen == []  # blocked on the row lock
        first.record_failed_sign_in(now=NOW)
        uow.users.update(first)
        uow.commit()
    waiter.join(timeout=5)
    assert seen == [1]


def test_fr_auth_02_refresh_token_rotation_round_trip(uow_factory: UowFactory) -> None:
    user = a_user()
    first = _token(user.id)
    second = _token(user.id, family_id=first.family_id)
    with uow_factory() as uow:
        uow.users.add(user)
        uow.refresh_tokens.add(first)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.refresh_tokens.get_by_hash(first.token_hash, for_update=True)
        assert stored == first
        uow.refresh_tokens.add(second)
        stored.mark_replaced(second.id, now=LATER)
        uow.refresh_tokens.update(stored)
        uow.commit()

    with uow_factory() as uow:
        rotated = uow.refresh_tokens.get_by_hash(first.token_hash)
        assert rotated is not None
        assert rotated.state(LATER) is RefreshTokenState.ROTATED
        assert rotated.replaced_by_id == second.id
        assert uow.refresh_tokens.get_by_hash("no-such-digest") is None


def test_r5_revoke_family_ends_every_live_token_in_it(uow_factory: UowFactory) -> None:
    user = a_user()
    first = _token(user.id)
    family = [first, _token(user.id, first.family_id), _token(user.id, first.family_id)]
    other_session = _token(user.id)
    first.mark_replaced(family[1].id, now=NOW)
    with uow_factory() as uow:
        uow.users.add(user)
        # Successors first: replaced_by_id is a foreign key to the newer token.
        for token in (family[1], family[2], first, other_session):
            uow.refresh_tokens.add(token)
        uow.commit()

    with uow_factory() as uow:
        # The already-rotated token keeps its revocation time; two live ones are revoked.
        assert uow.refresh_tokens.revoke_family(family[0].family_id, now=LATER) == 2
        uow.commit()

    with uow_factory() as uow:
        states = [uow.refresh_tokens.get_by_hash(t.token_hash) for t in family]
        assert [s.state(LATER) for s in states if s] == [
            RefreshTokenState.ROTATED,
            RefreshTokenState.REVOKED,
            RefreshTokenState.REVOKED,
        ]
        untouched = uow.refresh_tokens.get_by_hash(other_session.token_hash)
        assert untouched is not None and untouched.state(LATER) is RefreshTokenState.ACTIVE


def test_refresh_token_digest_is_unique_and_update_needs_a_row(uow_factory: UowFactory) -> None:
    user = a_user()
    with uow_factory() as uow:
        uow.users.add(user)
        uow.refresh_tokens.add(_token(user.id, digest="d" * 64))
        with pytest.raises(NotFound):
            uow.refresh_tokens.update(_token(user.id))
        with pytest.raises(IntegrityError, match="uq_refresh_tokens_token_hash"):
            uow.refresh_tokens.add(_token(user.id, digest="d" * 64))


def test_clinic_access_lists_only_active_memberships_by_clinic_name(
    uow_factory: UowFactory,
) -> None:
    user = a_user()
    zeta, alpha, gone, pending = (
        a_clinic(name="Zeta Sample Clinic"),
        a_clinic(name="Alpha Sample Clinic"),
        a_clinic(),
        a_clinic(),
    )
    with uow_factory() as uow:
        uow.users.add(user)
        for clinic in (zeta, alpha, gone, pending):
            uow.clinics.add(clinic)
        uow.tenant(zeta.id).memberships.add(a_membership(zeta.id, user.id, Role.DOCTOR))
        alpha_m = a_membership(alpha.id, user.id, Role.OWNER)
        uow.tenant(alpha.id).memberships.add(alpha_m)
        left = a_membership(gone.id, user.id, Role.FRONT_DESK)
        left.deactivate(active_owner_count=1, now=NOW)
        uow.tenant(gone.id).memberships.add(left)
        uow.tenant(pending.id).memberships.add(a_membership(pending.id, user.id, active=False))
        colleague = a_user()  # another user in the same clinic: the read is keyed by user
        uow.users.add(colleague)
        uow.tenant(alpha.id).memberships.add(a_membership(alpha.id, colleague.id))
        uow.commit()

    with uow_factory() as uow:
        access = uow.clinic_access.list_active_for_user(user.id)
        assert [(a.clinic_name, a.role) for a in access] == [
            ("Alpha Sample Clinic", Role.OWNER),
            ("Zeta Sample Clinic", Role.DOCTOR),
        ]
        assert access[0].membership_id == alpha_m.id
        assert access[0].clinic_status is ClinicStatus.ONBOARDING
        assert uow.clinic_access.list_active_for_user(new_id()) == []
