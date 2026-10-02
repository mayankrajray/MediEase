"""User and ClinicMembership rules (FR-ORG-03, FR-ORG-04; spec R9)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from mediease_api.domain.identity.membership import (
    ClinicMembership,
    LastOwnerError,
    MembershipStatus,
    Role,
)
from mediease_api.domain.identity.user import User, UserStatus
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from tests.builders import LATER, NOW, a_membership, a_user

# --- User -----------------------------------------------------------------------------


def test_user_with_email_only_or_phone_only() -> None:
    by_email = User.create(
        id=uuid4(), full_name="Sample Owner", email=EmailAddress.parse("o@example.test"), now=NOW
    )
    by_phone = User.create(
        id=uuid4(), full_name="Sample Desk", phone=PhoneNumber.parse("9000000002"), now=NOW
    )
    assert by_email.phone is None and by_phone.email is None
    assert by_email.status is UserStatus.ACTIVE
    assert not by_email.is_platform_ops


def test_user_needs_an_email_or_a_phone() -> None:
    with pytest.raises(InvalidValue, match="email address or a phone number"):
        User.create(id=uuid4(), full_name="Sample", now=NOW)


def test_user_disable_and_enable() -> None:
    user = a_user()
    user.disable(now=LATER)
    assert user.status is UserStatus.DISABLED
    assert user.updated_at == LATER
    with pytest.raises(InvalidTransition):
        user.disable(now=LATER)

    user.enable(now=LATER)
    assert user.status is UserStatus.ACTIVE
    with pytest.raises(InvalidTransition):
        user.enable(now=LATER)


# --- ClinicMembership --------------------------------------------------------------------


def test_fr_org_03_membership_starts_invited_then_activates() -> None:
    membership = ClinicMembership.invite(
        id=uuid4(), clinic_id=uuid4(), user_id=uuid4(), role=Role.DOCTOR, now=NOW
    )
    assert membership.status is MembershipStatus.INVITED
    membership.activate(now=LATER)
    assert membership.status is MembershipStatus.ACTIVE
    assert membership.updated_at == LATER
    with pytest.raises(InvalidTransition):
        membership.activate(now=LATER)


def test_fr_org_04_owner_changes_a_members_role() -> None:
    membership = a_membership(uuid4(), uuid4(), Role.FRONT_DESK)
    membership.change_role(Role.DOCTOR, active_owner_count=1, now=LATER)
    assert membership.role is Role.DOCTOR
    assert membership.updated_at == LATER


def test_changing_to_the_same_role_is_a_no_op() -> None:
    membership = a_membership(uuid4(), uuid4(), Role.OWNER)
    membership.change_role(Role.OWNER, active_owner_count=1, now=LATER)
    assert membership.updated_at == NOW


def test_r9_last_active_owner_cannot_be_demoted() -> None:
    owner = a_membership(uuid4(), uuid4(), Role.OWNER)
    with pytest.raises(LastOwnerError) as excinfo:
        owner.change_role(Role.DOCTOR, active_owner_count=1, now=LATER)
    assert excinfo.value.code == "CLN_LAST_OWNER"
    assert owner.role is Role.OWNER


def test_r9_last_active_owner_cannot_be_deactivated() -> None:
    owner = a_membership(uuid4(), uuid4(), Role.OWNER)
    with pytest.raises(LastOwnerError):
        owner.deactivate(active_owner_count=1, now=LATER)
    assert owner.status is MembershipStatus.ACTIVE


def test_r9_an_owner_can_leave_when_another_owner_remains() -> None:
    owner = a_membership(uuid4(), uuid4(), Role.OWNER)
    owner.change_role(Role.DOCTOR, active_owner_count=2, now=LATER)
    assert owner.role is Role.DOCTOR


def test_r9_an_invited_owner_is_not_an_active_owner() -> None:
    invited_owner = a_membership(uuid4(), uuid4(), Role.OWNER, active=False)
    assert not invited_owner.is_active_owner
    invited_owner.deactivate(active_owner_count=0, now=LATER)
    assert invited_owner.status is MembershipStatus.DEACTIVATED


def test_fr_org_04_deactivated_membership_is_final() -> None:
    membership = a_membership(uuid4(), uuid4())
    membership.deactivate(active_owner_count=1, now=LATER)
    assert membership.status is MembershipStatus.DEACTIVATED
    with pytest.raises(InvalidTransition):
        membership.deactivate(active_owner_count=1, now=LATER)
    with pytest.raises(InvalidTransition):
        membership.change_role(Role.OWNER, active_owner_count=1, now=LATER)
    with pytest.raises(InvalidTransition):
        membership.activate(now=LATER)
