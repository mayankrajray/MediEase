"""Invitations, the password rule and the onboarding checklist (M1-P5; R9, R12)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.membership import (
    INVITE_TTL,
    ClinicMembership,
    InviteState,
    MembershipStatus,
    Role,
)
from mediease_api.domain.identity.password import MIN_PASSWORD_LENGTH, validate_password
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from tests.builders import LATER, NOW, a_membership, new_id

DIGEST = "d" * 64

# --- Invitations ------------------------------------------------------------------------------


def _invited() -> ClinicMembership:
    return ClinicMembership.invite(
        id=new_id(), clinic_id=new_id(), user_id=new_id(), role=Role.OWNER, now=NOW
    )


def test_fr_org_04_an_invited_membership_carries_its_pending_invitation() -> None:
    membership = _invited()
    assert membership.invite_state(NOW) is InviteState.NONE

    membership.issue_invite(DIGEST, now=NOW)
    assert membership.invite_token_hash == DIGEST
    assert membership.invite_expires_at == NOW + INVITE_TTL
    assert membership.invite_state(NOW) is InviteState.PENDING


def test_fr_org_04_accepting_an_invitation_activates_the_membership() -> None:
    membership = _invited()
    membership.issue_invite(DIGEST, now=NOW)

    membership.accept_invite(now=LATER)

    assert membership.status is MembershipStatus.ACTIVE
    assert membership.invite_accepted_at == LATER
    # The digest stays, so a replay is "already used" rather than "not found".
    assert membership.invite_token_hash == DIGEST
    assert membership.invite_state(LATER) is InviteState.ACCEPTED


def test_an_invitation_can_only_be_accepted_once() -> None:
    membership = _invited()
    membership.issue_invite(DIGEST, now=NOW)
    membership.accept_invite(now=NOW)

    with pytest.raises(InvalidTransition):
        membership.accept_invite(now=LATER)


def test_an_expired_invitation_cannot_be_accepted() -> None:
    membership = _invited()
    membership.issue_invite(DIGEST, now=NOW)
    expired_at = NOW + INVITE_TTL + timedelta(seconds=1)

    assert membership.invite_state(expired_at) is InviteState.EXPIRED
    with pytest.raises(InvalidTransition):
        membership.accept_invite(now=expired_at)


def test_re_inviting_replaces_the_secret_and_its_expiry() -> None:
    membership = _invited()
    membership.issue_invite(DIGEST, now=NOW)
    membership.issue_invite("e" * 64, now=LATER)

    assert membership.invite_token_hash == "e" * 64
    assert membership.invite_expires_at == LATER + INVITE_TTL


def test_only_an_invited_membership_can_be_invited_again() -> None:
    membership = a_membership(new_id(), new_id(), Role.DOCTOR)  # already ACTIVE
    with pytest.raises(InvalidTransition):
        membership.issue_invite(DIGEST, now=LATER)


def test_deactivating_a_member_kills_a_pending_invitation() -> None:
    membership = _invited()
    membership.issue_invite(DIGEST, now=NOW)

    membership.deactivate(active_owner_count=2, now=LATER)

    assert membership.status is MembershipStatus.DEACTIVATED
    assert membership.invite_token_hash is None
    assert membership.invite_state(LATER) is InviteState.NONE


def test_r9_the_last_active_owner_cannot_be_deactivated() -> None:
    owner = a_membership(new_id(), new_id(), Role.OWNER)
    with pytest.raises(Exception, match="at least one owner"):
        owner.deactivate(active_owner_count=1, now=LATER)
    assert owner.status is MembershipStatus.ACTIVE


# --- Password rule ----------------------------------------------------------------------------


def test_fr_auth_01_a_chosen_password_has_a_minimum_length() -> None:
    assert validate_password("a" * MIN_PASSWORD_LENGTH) == "a" * MIN_PASSWORD_LENGTH
    with pytest.raises(InvalidValue) as excinfo:
        validate_password("a" * (MIN_PASSWORD_LENGTH - 1))
    assert excinfo.value.field == "password"
    assert "a" * 11 not in str(excinfo.value.details)  # never echoed


@pytest.mark.parametrize("password", [" " * 20, "x" * 1025], ids=["only-spaces", "absurdly-long"])
def test_a_password_that_is_blank_or_unbounded_is_refused(password: str) -> None:
    with pytest.raises(InvalidValue):
        validate_password(password)


# --- Onboarding checklist (R12) ---------------------------------------------------------------


def test_fr_ops_04_a_checklist_times_each_step() -> None:
    checklist = OnboardingChecklist.start(id=new_id(), clinic_id=new_id(), now=NOW)
    assert checklist.completed_steps == ()

    assert checklist.record(OnboardingStep.CLINIC_CREATED, now=NOW) is True
    assert checklist.record(OnboardingStep.DOCTORS_ADDED, now=LATER) is True

    assert checklist.at(OnboardingStep.DOCTORS_ADDED) == LATER
    assert checklist.completed_steps == (
        OnboardingStep.CLINIC_CREATED,
        OnboardingStep.DOCTORS_ADDED,
    )
    assert checklist.elapsed(OnboardingStep.DOCTORS_ADDED) == LATER - NOW
    assert checklist.elapsed(OnboardingStep.STAFF_INVITED) is None


def test_r12_a_repeated_step_does_not_move_its_timestamp() -> None:
    checklist = OnboardingChecklist.start(id=new_id(), clinic_id=new_id(), now=NOW)
    checklist.record(OnboardingStep.DOCTORS_ADDED, now=NOW)

    assert checklist.record(OnboardingStep.DOCTORS_ADDED, now=LATER) is False
    assert checklist.at(OnboardingStep.DOCTORS_ADDED) == NOW


def test_every_step_names_the_column_it_is_stored_in() -> None:
    """The enum value is the column name, so the mapping cannot drift (repositories rely on it)."""
    assert [step.value for step in OnboardingStep] == [
        "clinic_created_at",
        "doctors_added_at",
        "staff_invited_at",
        "patients_imported_at",
        "first_appointment_at",
        "first_prescription_at",
    ]
