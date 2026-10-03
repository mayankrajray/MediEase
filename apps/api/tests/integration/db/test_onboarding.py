"""Invitations and onboarding checklists against real PostgreSQL (M1-P5; R12).

The invitation round-trips on the membership, the digest is unique and never
stored in clear, the platform lookup finds it without a clinic context, and a
checklist belongs to exactly one clinic.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from mediease_api.domain.clinics.onboarding import OnboardingChecklist, OnboardingStep
from mediease_api.domain.identity.membership import InviteState, MembershipStatus, Role
from mediease_api.domain.shared.errors import NotFound
from tests.builders import LATER, NOW, a_clinic, a_membership, a_user, new_id
from tests.conftest import UowFactory

DIGEST = "d" * 64


def _clinic_with_invited_owner(uow_factory: UowFactory, digest: str = DIGEST) -> tuple:
    clinic, user = a_clinic(), a_user()
    membership = a_membership(clinic.id, user.id, Role.OWNER, active=False)
    membership.issue_invite(digest, now=NOW)
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(user)
        uow.tenant(clinic.id).memberships.add(membership)
        uow.commit()
    return clinic, user, membership


def test_fr_org_04_an_invitation_round_trips_on_the_membership(uow_factory: UowFactory) -> None:
    clinic, _, membership = _clinic_with_invited_owner(uow_factory)

    with uow_factory() as uow:
        stored = uow.tenant(clinic.id).memberships.get(membership.id)
        assert stored is not None
        assert stored.status is MembershipStatus.INVITED
        assert stored.invite_token_hash == DIGEST
        assert stored.invite_expires_at == membership.invite_expires_at
        assert stored.invite_state(NOW) is InviteState.PENDING


def test_the_invitation_is_found_by_its_digest_without_a_clinic_context(
    uow_factory: UowFactory,
) -> None:
    clinic, _, membership = _clinic_with_invited_owner(uow_factory)

    with uow_factory() as uow:
        found = uow.staff_invites.get_by_invite_digest(DIGEST)
        assert found is not None
        assert (found.id, found.clinic_id) == (membership.id, clinic.id)
        assert uow.staff_invites.get_by_invite_digest("e" * 64) is None


def test_accepting_an_invitation_is_persisted(uow_factory: UowFactory) -> None:
    clinic, _, membership = _clinic_with_invited_owner(uow_factory)

    with uow_factory() as uow:
        found = uow.staff_invites.get_by_invite_digest(DIGEST)
        assert found is not None
        found.accept_invite(now=LATER)
        uow.tenant(clinic.id).memberships.update(found)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.tenant(clinic.id).memberships.get(membership.id)
        assert stored is not None
        assert stored.status is MembershipStatus.ACTIVE
        assert stored.invite_accepted_at == LATER
        assert stored.invite_state(LATER) is InviteState.ACCEPTED


def test_two_memberships_cannot_share_an_invitation_digest(uow_factory: UowFactory) -> None:
    clinic, _, _ = _clinic_with_invited_owner(uow_factory)
    other_user = a_user()
    second = a_membership(clinic.id, other_user.id, Role.FRONT_DESK, active=False)
    second.issue_invite(DIGEST, now=NOW)

    with uow_factory() as uow:
        uow.users.add(other_user)
        with pytest.raises(IntegrityError, match="uq_clinic_memberships_invite_token_hash"):
            uow.tenant(clinic.id).memberships.add(second)


# --- Onboarding checklist ---------------------------------------------------------------------


def test_fr_ops_04_a_checklist_round_trips_with_its_steps(uow_factory: UowFactory) -> None:
    clinic = a_clinic()
    checklist = OnboardingChecklist.start(id=new_id(), clinic_id=clinic.id, now=NOW)
    checklist.record(OnboardingStep.CLINIC_CREATED, now=NOW)
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.tenant(clinic.id).checklist.add(checklist)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.tenant(clinic.id).checklist.get()
        assert stored is not None
        assert stored.started_at == NOW
        assert stored.completed_steps == (OnboardingStep.CLINIC_CREATED,)
        stored.record(OnboardingStep.DOCTORS_ADDED, now=LATER)
        uow.tenant(clinic.id).checklist.update(stored)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.tenant(clinic.id).checklist.get()
        assert stored is not None
        assert stored.at(OnboardingStep.DOCTORS_ADDED) == LATER
        assert stored.at(OnboardingStep.PATIENTS_IMPORTED) is None
        # R8: another clinic's scope sees no checklist at all.
        assert uow.tenant(new_id()).checklist.get() is None


def test_a_checklist_update_needs_its_own_row(uow_factory: UowFactory) -> None:
    clinic = a_clinic()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        with pytest.raises(NotFound):
            uow.tenant(clinic.id).checklist.update(
                OnboardingChecklist.start(id=new_id(), clinic_id=clinic.id, now=NOW)
            )


def test_fr_ops_01_the_ops_clinic_list_pairs_clinics_with_their_checklists(
    uow_factory: UowFactory,
) -> None:
    with_checklist, without = a_clinic(name="Alpha Sample Clinic"), a_clinic(name="Beta Clinic")
    checklist = OnboardingChecklist.start(id=new_id(), clinic_id=with_checklist.id, now=NOW)
    checklist.record(OnboardingStep.CLINIC_CREATED, now=NOW)
    with uow_factory() as uow:
        uow.clinics.add(with_checklist)
        uow.clinics.add(without)
        uow.tenant(with_checklist.id).checklist.add(checklist)
        uow.commit()

    with uow_factory() as uow:
        listed = uow.clinics.list_onboarding()

    by_id = {clinic.id: steps for clinic, steps in listed}
    assert set(by_id) == {with_checklist.id, without.id}
    assert by_id[without.id] is None
    found = by_id[with_checklist.id]
    assert found is not None and found.completed_steps == (OnboardingStep.CLINIC_CREATED,)
