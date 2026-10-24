"""Account links and portal invites (M6b-P1; patient portal spec R1-R4, R8; decision 1A)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from mediease_api.domain.portal.link import (
    INVITE_TTL,
    AlreadyLinked,
    LinkMethod,
    PatientAccountLink,
    PatientPortalInvite,
    PortalInviteInvalid,
    RevokedBy,
    check_can_link,
)
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, new_id


def _link() -> PatientAccountLink:
    return PatientAccountLink.create(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        account_id=new_id(),
        method=LinkMethod.RX_LINK,
        created_by_user_id=None,
        now=NOW,
    )


def _invite() -> PatientPortalInvite:
    return PatientPortalInvite.create(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        token_hash="a" * 64,
        created_by=new_id(),
        now=NOW,
    )


def test_r8_a_link_is_revoked_once_and_says_who() -> None:
    link = _link()
    assert link.is_active
    assert link.revoke(RevokedBy.STAFF, NOW + timedelta(hours=1)) is True
    assert (link.is_active, link.revoked_by) == (False, RevokedBy.STAFF)
    assert link.revoke(RevokedBy.PATIENT, NOW + timedelta(hours=2)) is False
    assert (link.revoked_at, link.revoked_by) == (NOW + timedelta(hours=1), RevokedBy.STAFF)


def test_r4_one_active_link_each_way() -> None:
    check_can_link(record_link=None, account_link=None)
    with pytest.raises(AlreadyLinked):
        check_can_link(record_link=_link(), account_link=None)
    with pytest.raises(AlreadyLinked) as excinfo:
        check_can_link(record_link=None, account_link=_link())
    assert excinfo.value.code == "PRT_ALREADY_LINKED"


def test_r1_an_invite_lasts_seven_days() -> None:
    invite = _invite()
    assert invite.expires_at == NOW + INVITE_TTL == NOW + timedelta(days=7)
    assert invite.is_usable(NOW + timedelta(days=7) - timedelta(seconds=1))
    assert not invite.is_usable(NOW + timedelta(days=7))
    with pytest.raises(PortalInviteInvalid):
        invite.use(new_id(), NOW + timedelta(days=8))


def test_r3_an_invite_is_used_once() -> None:
    invite, account = _invite(), new_id()
    invite.use(account, NOW)
    assert (invite.used_at, invite.used_by_account_id, invite.is_pending) == (NOW, account, False)
    with pytest.raises(PortalInviteInvalid) as excinfo:
        invite.use(new_id(), NOW)
    assert excinfo.value.code == "PRT_INVITE_INVALID"
    assert invite.supersede(NOW) is False  # a used invite stays used


def test_a_new_invite_supersedes_the_pending_one() -> None:
    invite = _invite()
    assert invite.supersede(NOW + timedelta(minutes=1)) is True
    assert not invite.is_usable(NOW + timedelta(minutes=2))
    assert invite.supersede(NOW + timedelta(minutes=3)) is False
    with pytest.raises(PortalInviteInvalid):
        invite.use(new_id(), NOW + timedelta(minutes=4))


def test_times_must_be_utc() -> None:
    with pytest.raises(InvalidValue):
        _invite().is_usable(NOW.replace(tzinfo=None))
