"""Credentials, refresh tokens and clinic access against real PostgreSQL (M1-P2, M1-P3).

Proves the sign-in state round-trips, refresh tokens rotate and revoke by
family, row locks really serialise concurrent sign-ins, and the reads M1-P3
checks on every request return what authorisation needs: whether a session's
token family is still live, which clinics a user may work in (with a linked
doctor profile where there is one), and a clinic's staff directory.
"""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.membership import MembershipStatus, Role
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.identity.session import RefreshToken, RefreshTokenState
from mediease_api.domain.shared.errors import NotFound
from tests.builders import LATER, NOW, a_clinic, a_doctor, a_membership, a_user, new_id
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


def test_r7_is_family_live_follows_rotation_revocation_and_expiry(
    uow_factory: UowFactory,
) -> None:
    """The per-request session check (M1-P3): live while one token in the family is usable."""
    user = a_user()
    first = _token(user.id)
    successor = _token(user.id, first.family_id)
    first.mark_replaced(successor.id, now=NOW)
    with uow_factory() as uow:
        uow.users.add(user)
        uow.refresh_tokens.add(successor)
        uow.refresh_tokens.add(first)
        uow.commit()

    with uow_factory() as uow:
        # A rotated token is spent, but its successor keeps the session alive.
        assert uow.refresh_tokens.is_family_live(first.family_id, now=LATER) is True
        assert uow.refresh_tokens.is_family_live(new_id(), now=LATER) is False
        # Every token expired: access ends without anyone signing out.
        expired_at = NOW + timedelta(days=15)
        assert uow.refresh_tokens.is_family_live(first.family_id, now=expired_at) is False
        uow.refresh_tokens.revoke_family(first.family_id, now=LATER)
        uow.commit()

    with uow_factory() as uow:
        assert uow.refresh_tokens.is_family_live(first.family_id, now=LATER) is False


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


def test_clinic_access_reports_a_linked_doctor_profile_per_clinic(
    uow_factory: UowFactory,
) -> None:
    """An owner who is also a doctor may write clinical records (spec §8) — in that clinic only."""
    user = a_user()
    prescribing, desk_only = a_clinic(name="Alpha Sample Clinic"), a_clinic(name="Beta Clinic")
    with uow_factory() as uow:
        uow.users.add(user)
        for clinic in (prescribing, desk_only):
            uow.clinics.add(clinic)
            uow.tenant(clinic.id).memberships.add(a_membership(clinic.id, user.id, Role.OWNER))
        uow.tenant(prescribing.id).doctors.add(a_doctor(prescribing.id, user_id=user.id))
        # Another clinic's doctor profile for somebody else must not count.
        colleague = a_user()
        uow.users.add(colleague)
        uow.tenant(desk_only.id).doctors.add(a_doctor(desk_only.id, user_id=colleague.id))
        uow.commit()

    with uow_factory() as uow:
        access = uow.clinic_access.list_active_for_user(user.id)
        assert [(a.clinic_name, a.has_doctor_profile) for a in access] == [
            ("Alpha Sample Clinic", True),
            ("Beta Clinic", False),
        ]
        assert Permission.CLINICAL_WRITE in access[0].permissions
        assert Permission.CLINICAL_WRITE not in access[1].permissions


def test_clinic_access_ignores_a_deactivated_doctor_profile(uow_factory: UowFactory) -> None:
    user, clinic = a_user(), a_clinic()
    doctor = a_doctor(clinic.id, user_id=user.id)
    doctor.deactivate(now=LATER)
    with uow_factory() as uow:
        uow.users.add(user)
        uow.clinics.add(clinic)
        uow.tenant(clinic.id).memberships.add(a_membership(clinic.id, user.id, Role.OWNER))
        uow.tenant(clinic.id).doctors.add(doctor)
        uow.commit()

    with uow_factory() as uow:
        assert uow.clinic_access.list_active_for_user(user.id)[0].has_doctor_profile is False


def test_list_staff_returns_every_membership_of_the_clinic_by_name(
    uow_factory: UowFactory,
) -> None:
    clinic, other = a_clinic(), a_clinic()
    owner = a_user(full_name="Anita Sample")
    invited = a_user(full_name="Zara Sample")
    outsider = a_user(full_name="Aaron Other")
    with uow_factory() as uow:
        for clinic_row in (clinic, other):
            uow.clinics.add(clinic_row)
        for user in (owner, invited, outsider):
            uow.users.add(user)
        uow.tenant(clinic.id).memberships.add(a_membership(clinic.id, owner.id, Role.OWNER))
        uow.tenant(clinic.id).memberships.add(
            a_membership(clinic.id, invited.id, Role.FRONT_DESK, active=False)
        )
        uow.tenant(other.id).memberships.add(a_membership(other.id, outsider.id, Role.OWNER))
        uow.commit()

    with uow_factory() as uow:
        staff = uow.tenant(clinic.id).memberships.list_staff()
        assert [(s.full_name, s.role, s.status) for s in staff] == [
            ("Anita Sample", Role.OWNER, MembershipStatus.ACTIVE),
            ("Zara Sample", Role.FRONT_DESK, MembershipStatus.INVITED),
        ]
        assert staff[0].user_id == owner.id
        # R8: another clinic's staff are not reachable through this scope.
        assert uow.tenant(new_id()).memberships.list_staff() == []
