"""Onboarding a clinic end to end (FR-OPS-01/04, FR-ORG-01/02/04; spec I1, I2, R9, R12).

The first test is the M1 exit criterion: an ops user creates a clinic, adds a
doctor and invites the owner; the owner sets a password, is signed in, and
invites the front desk, who accepts and sees only what their role allows.
The rest covers what must go wrong safely.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.test import TestResponse

from mediease_api.adapters.security.refresh_secrets import Sha256RefreshTokenSecrets
from mediease_api.domain.identity.membership import Role
from tests.builders import NOW, a_membership, a_user
from tests.conftest import DEMO_PASSWORD, UowFactory, World
from tests.integration.test_team_http import InviteMailbox, invite_token

OPS_CLINICS = "/api/v1/ops/clinics"
CLINIC = "/api/v1/clinic"
STAFF = "/api/v1/clinic/staff"
INVITES = "/api/v1/auth/invites"
PASSWORD = "a-new-staff-password"  # gitleaks:allow (synthetic test value)
SessionFactory = sessionmaker[Session]


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def _post(client: FlaskClient, path: str, body: dict[str, Any]) -> TestResponse:
    return client.post(path, json=body, headers=_csrf(client))


def _patch(client: FlaskClient, path: str, body: dict[str, Any]) -> TestResponse:
    return client.patch(path, json=body, headers=_csrf(client))


def _token_from(resp: TestResponse) -> str:
    return resp.get_json()["accept_url"].rsplit("/", 1)[1]


def _new_clinic(client: FlaskClient, slug: str = "new-sample-clinic") -> dict[str, Any]:
    resp = _post(
        client,
        OPS_CLINICS,
        {
            "name": "New Sample Clinic",
            "slug": slug,
            "phone": "9000012345",
            "city": "Sample City",
            "pincode": "560002",
            "specialties": ["General Medicine"],
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return dict(resp.get_json())


def _invite(
    client: FlaskClient, clinic_id: str, role: Role, email: str, name: str = "Invited Person"
) -> TestResponse:
    return _post(
        client,
        f"{OPS_CLINICS}/{clinic_id}/staff-invites",
        {"full_name": name, "role": role.value, "email": email},
    )


def _accept(client: FlaskClient, token: str, password: str = PASSWORD) -> TestResponse:
    return client.post(f"{INVITES}/{token}/accept", json={"password": password})


def _sign_in(client: FlaskClient, email: str, password: str) -> int:
    return client.post(
        "/api/v1/auth/sign-in", json={"identifier": email, "password": password}
    ).status_code


def _events(session_factory: SessionFactory, action: str) -> list[dict[str, Any]]:
    with session_factory() as session:
        rows = session.execute(
            text("SELECT * FROM audit_events WHERE action = :action ORDER BY occurred_at"),
            {"action": action},
        )
        return [dict(row) for row in rows.mappings()]


# --- The M1 exit criterion --------------------------------------------------------------------


def test_fr_ops_01_ops_onboards_a_clinic_and_every_role_signs_in(
    world: World, session_factory: SessionFactory, uow_factory: UowFactory
) -> None:
    ops = world.client_for(world.ops)
    mailbox = InviteMailbox(uow_factory)

    clinic = _new_clinic(ops)
    assert clinic["status"] == "ONBOARDING"

    doctor = _post(
        ops,
        f"{OPS_CLINICS}/{clinic['id']}/doctors",
        {
            "display_name": "Dr. New Sample",
            "qualification": "MBBS",
            "registration_number": "NEW-0001",
            "registration_council": "Sample State Medical Council",
        },
    )
    assert doctor.status_code == 201

    invited = _invite(ops, clinic["id"], Role.OWNER, "new-owner@example.test", "New Owner")
    assert invited.status_code == 201
    assert invited.get_json()["status"] == "INVITED"
    assert invited.get_json()["accept_url"].startswith("http")

    # The owner has no session: they look at the invitation, then accept it.
    invitee = world.anonymous()
    token = _token_from(invited)
    described = invitee.get(f"{INVITES}/{token}")
    assert described.status_code == 200
    assert described.get_json() == {
        "clinic_name": "New Sample Clinic",
        "full_name": "New Owner",
        "role": "OWNER",
        "expires_at": described.get_json()["expires_at"],
        "has_password": False,
    }

    accepted = _accept(invitee, token)
    assert accepted.status_code == 200
    assert accepted.get_json()["memberships"][0]["role"] == "OWNER"
    # Accepting signed them in: the cookies are set and /me works.
    assert invitee.get("/api/v1/me").status_code == 200

    # I1: the clinic is active now that it has an active owner.
    assert invitee.get(CLINIC).get_json()["status"] == "ACTIVE"

    # The owner invites the front desk by email (M6a-P5: the worker sends it), who accepts the
    # emailed link and signs in.
    desk_invite = _post(
        invitee,
        STAFF,
        {"full_name": "New Desk", "role": "FRONT_DESK", "email": "new-desk@example.test"},
    )
    assert desk_invite.status_code == 201
    assert desk_invite.get_json()["accept_url"] is None
    desk = world.anonymous()
    assert _accept(desk, invite_token(mailbox.deliver()[0])).status_code == 200
    assert desk.get(CLINIC).status_code == 200
    # ... and sees only what the front desk may see.
    assert desk.get(STAFF).status_code == 403

    # Every step is in the audit trail, with ops and staff as the actors.
    assert [e["actor_type"] for e in _events(session_factory, "clinic.created")] == ["OPS"]
    assert [e["actor_type"] for e in _events(session_factory, "doctor.added")] == ["OPS"]
    invites = _events(session_factory, "staff.invited")
    assert [e["actor_type"] for e in invites] == ["OPS", "STAFF"]
    assert [e["metadata"]["role"] for e in invites] == ["OWNER", "FRONT_DESK"]
    assert len(_events(session_factory, "staff.accepted")) == 2
    assert [e["metadata"] for e in _events(session_factory, "clinic.activated")] == [
        {"reason": "owner_accepted"}
    ]


def test_fr_ops_04_r12_the_checklist_times_the_first_of_each_step(
    world: World, session_factory: SessionFactory
) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops)
    doctor_body = {
        "display_name": "Dr. One",
        "qualification": "MBBS",
        "registration_number": "ONE-1",
        "registration_council": "Sample State Medical Council",
    }
    _post(ops, f"{OPS_CLINICS}/{clinic['id']}/doctors", doctor_body)
    _post(
        ops,
        f"{OPS_CLINICS}/{clinic['id']}/doctors",
        {**doctor_body, "display_name": "Dr. Two", "registration_number": "TWO-2"},
    )
    _invite(ops, clinic["id"], Role.OWNER, "checklist-owner@example.test")

    detail = ops.get(f"{OPS_CLINICS}/{clinic['id']}").get_json()
    checklist = detail["onboarding"]
    assert checklist["clinic_created_at"] is not None
    assert checklist["doctors_added_at"] is not None
    assert checklist["staff_invited_at"] is not None
    assert checklist["patients_imported_at"] is None
    assert detail["doctor_count"] == 2

    # R12: the second doctor did not move the timestamp.
    with session_factory() as session:
        stamps = session.execute(
            text("SELECT doctors_added_at FROM onboarding_checklists WHERE clinic_id = :id"),
            {"id": UUID(clinic["id"])},
        ).scalar_one()
    assert stamps.isoformat() == checklist["doctors_added_at"]


def test_fr_ops_01_the_ops_list_shows_every_clinic_with_its_state(world: World) -> None:
    ops = world.client_for(world.ops)
    created = _new_clinic(ops)

    listed = ops.get(OPS_CLINICS).get_json()["items"]
    by_id = {entry["id"]: entry for entry in listed}
    # Clinics A, B and the suspended one from the fixture, plus the new one.
    assert len(listed) == 4
    assert by_id[created["id"]]["onboarding"]["clinic_created_at"] is not None
    assert by_id[str(world.a.clinic.id)]["onboarding"] is None  # seeded without a checklist
    assert all("items" not in entry for entry in listed)


# --- What must go wrong safely ----------------------------------------------------------------


def test_a_duplicate_slug_is_refused(world: World) -> None:
    ops = world.client_for(world.ops)
    _new_clinic(ops, slug="taken-slug")
    resp = _post(ops, OPS_CLINICS, {"name": "Another Clinic", "slug": "taken-slug"})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CLN_SLUG_TAKEN"


def test_i2_inviting_an_existing_member_again_is_refused(world: World) -> None:
    ops = world.client_for(world.ops)
    assert world.a.desk.email is not None
    resp = _invite(ops, str(world.a.clinic.id), Role.DOCTOR, world.a.desk.email.value)
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CLN_MEMBER_EXISTS"


def test_spec_8_one_user_can_be_invited_by_a_second_clinic(
    world: World, session_factory: SessionFactory
) -> None:
    """A doctor who works at two clinics keeps one account and gets two memberships."""
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops, slug="second-clinic")
    assert world.a.doctor_user.email is not None

    invited = _invite(ops, clinic["id"], Role.DOCTOR, world.a.doctor_user.email.value)
    assert invited.status_code == 201
    assert invited.get_json()["user_id"] == str(world.a.doctor_user.id)
    # They already have a password, so the page asks for it instead of choosing a new one.
    described = world.anonymous().get(f"{INVITES}/{_token_from(invited)}")
    assert described.get_json()["has_password"] is True

    accepted = _accept(world.anonymous(), _token_from(invited), DEMO_PASSWORD)
    assert accepted.status_code == 200
    assert len(accepted.get_json()["memberships"]) == 2
    assert [e["metadata"]["account"] for e in _events(session_factory, "staff.accepted")] == [
        "existing"
    ]


def test_r13_the_invite_link_alone_cannot_take_over_an_existing_account(
    world: World, session_factory: SessionFactory
) -> None:
    """The regression for the M1-P5 hole: whoever holds the link must know the password.

    Somebody invites the email of a doctor who already works at clinic A and holds the link
    themselves, then tries to accept it with a password of their own choosing. From M6a-P5 an
    owner's invitation to an email address is emailed to that address and never shown, so the
    link-holder here is ops, whose invitations are still shown as a link (until M6c).
    """
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops, slug="takeover-attempt")
    assert world.a.doctor_user.email is not None
    invited = _invite(ops, clinic["id"], Role.DOCTOR, world.a.doctor_user.email.value, "Dr. Target")
    assert invited.status_code == 201, invited.get_json()
    token = _token_from(invited)

    takeover = _accept(world.anonymous(), token, "the-attackers-chosen-password")

    assert takeover.status_code == 401
    assert takeover.get_json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
    assert "set-cookie" not in {k.lower() for k in dict(takeover.headers)}
    # Nothing changed for the real user: the old password still works, the new one does not.
    assert _sign_in(world.anonymous(), world.a.doctor_user.email.value, DEMO_PASSWORD) == 200
    assert (
        _sign_in(
            world.anonymous(), world.a.doctor_user.email.value, "the-attackers-chosen-password"
        )
        == 401
    )
    # The invitation is still pending, so the real person can accept it later.
    assert _accept(world.anonymous(), token, DEMO_PASSWORD).status_code == 200
    failures = _events(session_factory, "auth.sign_in_failed")
    assert any(e["metadata"].get("via") == "invite" for e in failures)


def test_r13_accepting_for_an_existing_account_leaves_its_password_alone(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops, slug="third-clinic")
    assert world.a.doctor_user.email is not None
    email = world.a.doctor_user.email.value
    token = _token_from(_invite(ops, clinic["id"], Role.DOCTOR, email))

    assert _accept(world.anonymous(), token, DEMO_PASSWORD).status_code == 200

    assert _sign_in(world.anonymous(), email, DEMO_PASSWORD) == 200


def test_r13_wrong_passwords_on_an_invitation_count_towards_the_lockout(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops, slug="fourth-clinic")
    assert world.a.doctor_user.email is not None
    email = world.a.doctor_user.email.value
    token = _token_from(_invite(ops, clinic["id"], Role.DOCTOR, email))

    statuses = [_accept(world.anonymous(), token, f"wrong-guess-{n}").status_code for n in range(5)]

    assert statuses == [401, 401, 401, 401, 401]
    locked = _accept(world.anonymous(), token, DEMO_PASSWORD)  # even the right one is refused now
    assert locked.status_code == 423
    assert locked.get_json()["error"]["code"] == "AUTH_LOCKED"
    assert int(locked.headers["Retry-After"]) > 0
    # The lock is the account's, so sign-in is locked too: this endpoint is not a side door.
    assert _sign_in(world.anonymous(), email, DEMO_PASSWORD) == 423


def test_r13_a_person_with_no_active_membership_can_rejoin_with_their_password(
    world: World, uow_factory: UowFactory
) -> None:
    """Deactivated everywhere, then invited again: sign-in refuses them, so accepting must not."""
    desk = world.a.desk
    assert desk.email is not None
    with uow_factory() as uow:
        staff = uow.tenant(world.a.clinic.id).memberships
        membership = staff.get_for_user(desk.id)
        assert membership is not None
        membership.deactivate(active_owner_count=staff.count_active_owners(), now=NOW)
        staff.update(membership)
        uow.commit()
    assert _sign_in(world.anonymous(), desk.email.value, DEMO_PASSWORD) == 403

    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops, slug="rejoin-clinic")
    token = _token_from(_invite(ops, clinic["id"], Role.FRONT_DESK, desk.email.value))

    accepted = _accept(world.anonymous(), token, DEMO_PASSWORD)

    assert accepted.status_code == 200
    assert [m["clinic_id"] for m in accepted.get_json()["memberships"]] == [clinic["id"]]


def test_a_new_account_still_chooses_its_password_and_the_policy_applies(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops, slug="fifth-clinic")
    invited = _invite(ops, clinic["id"], Role.OWNER, "brand-new@example.test")

    assert _accept(world.anonymous(), _token_from(invited), "short").status_code == 422
    assert _accept(world.anonymous(), _token_from(invited), PASSWORD).status_code == 200
    assert _sign_in(world.anonymous(), "brand-new@example.test", PASSWORD) == 200


def test_re_inviting_retires_the_previous_link(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops)
    first = _invite(ops, clinic["id"], Role.OWNER, "re-invited@example.test")
    second = _invite(ops, clinic["id"], Role.OWNER, "re-invited@example.test")
    assert second.status_code == 201

    stale = world.anonymous().get(f"{INVITES}/{_token_from(first)}")
    assert stale.status_code == 404
    assert stale.get_json()["error"]["code"] == "CLN_INVITE_INVALID"
    assert _accept(world.anonymous(), _token_from(second)).status_code == 200


def test_an_accepted_invitation_cannot_be_used_twice(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops)
    token = _token_from(_invite(ops, clinic["id"], Role.OWNER, "once@example.test"))
    assert _accept(world.anonymous(), token).status_code == 200

    replayed = _accept(world.anonymous(), token)
    assert replayed.status_code == 410
    assert replayed.get_json()["error"]["code"] == "CLN_INVITE_USED"


def test_an_expired_invitation_tells_the_invitee_to_ask_again(
    world: World, uow_factory: UowFactory
) -> None:
    """Seeded with a known secret and an expiry in the past, so no clock tricks are needed."""
    token = "expired-invitation-token-for-tests"
    user = a_user(full_name="Stale Invitee", password_hash=None)
    membership = a_membership(world.a.clinic.id, user.id, Role.FRONT_DESK, active=False)
    membership.issue_invite(
        Sha256RefreshTokenSecrets().digest(token), now=NOW, ttl=timedelta(seconds=1)
    )
    with uow_factory() as uow:
        uow.users.add(user)
        uow.tenant(world.a.clinic.id).memberships.add(membership)
        uow.commit()

    described = world.anonymous().get(f"{INVITES}/{token}")
    assert described.status_code == 410
    assert described.get_json()["error"]["code"] == "CLN_INVITE_EXPIRED"
    assert _accept(world.anonymous(), token).status_code == 410


@pytest.mark.parametrize("token", ["not-a-real-token", "x" * 120])
def test_an_unknown_invitation_is_404(world: World, token: str) -> None:
    resp = world.anonymous().get(f"{INVITES}/{token}")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "CLN_INVITE_INVALID"


def test_fr_auth_01_a_weak_password_is_refused_without_echoing_it(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops)
    token = _token_from(_invite(ops, clinic["id"], Role.OWNER, "weak@example.test"))

    resp = _accept(world.anonymous(), token, password="short")
    assert resp.status_code == 422
    error = resp.get_json()["error"]
    assert error["code"] == "REQ_VALIDATION_FAILED"
    assert error["details"]["fields"] == [
        {"field": "password", "reason": "must be at least 12 characters"}
    ]
    assert "short" not in resp.get_data(as_text=True)
    # The invitation is still usable afterwards.
    assert _accept(world.anonymous(), token).status_code == 200


def test_an_invite_needs_an_email_or_a_phone(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops)
    resp = _post(
        ops,
        f"{OPS_CLINICS}/{clinic['id']}/staff-invites",
        {"full_name": "No Contact", "role": "DOCTOR"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "REQ_VALIDATION_FAILED"


def test_r1_an_invite_by_phone_alone_works(world: World) -> None:
    """Phone is a sign-in identifier too, so it is enough to invite somebody (R1)."""
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops)
    invited = _post(
        ops,
        f"{OPS_CLINICS}/{clinic['id']}/staff-invites",
        {"full_name": "Phone Owner", "role": "OWNER", "phone": "90000 54321"},
    )
    assert invited.status_code == 201

    accepted = _accept(world.anonymous(), _token_from(invited))
    assert accepted.status_code == 200
    assert accepted.get_json()["user"]["phone_e164"] == "+919000054321"
    assert accepted.get_json()["user"]["email"] is None


def test_an_invite_response_never_repeats_the_secret_in_logs(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops)
    capsys.readouterr()
    invited = _invite(ops, clinic["id"], Role.OWNER, "quiet@example.test")

    token = _token_from(invited)
    assert token not in capsys.readouterr().out


def test_a_disabled_account_cannot_accept_an_invitation(
    world: World, uow_factory: UowFactory
) -> None:
    ops = world.client_for(world.ops)
    clinic = _new_clinic(ops)
    invited = _invite(ops, clinic["id"], Role.OWNER, "disabled@example.test")
    token = _token_from(invited)

    with uow_factory() as uow:
        user = uow.users.get(UUID(invited.get_json()["user_id"]))
        assert user is not None
        user.disable(now=user.updated_at)
        uow.users.update(user)
        uow.commit()

    resp = _accept(world.anonymous(), token)
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "AUTH_ACCOUNT_DISABLED"


def test_adding_a_doctor_to_an_unknown_clinic_is_404(world: World) -> None:
    ops = world.client_for(world.ops)
    unknown = "00000000-0000-0000-0000-000000000008"
    resp = _post(
        ops,
        f"{OPS_CLINICS}/{unknown}/doctors",
        {
            "display_name": "Dr. Nowhere",
            "qualification": "MBBS",
            "registration_number": "NO-1",
            "registration_council": "Sample State Medical Council",
        },
    )
    assert resp.status_code == 404


# --- R10: who may use the ops API -------------------------------------------------------------


def test_r10_clinic_staff_cannot_use_the_ops_api(world: World) -> None:
    owner = world.client_for(world.a.owner)
    assert owner.get(OPS_CLINICS).status_code == 403
    assert _post(owner, OPS_CLINICS, {"name": "Mine", "slug": "mine-clinic"}).status_code == 403


def test_an_unknown_clinic_is_404_for_ops(world: World) -> None:
    ops = world.client_for(world.ops)
    unknown = "00000000-0000-0000-0000-000000000009"
    assert ops.get(f"{OPS_CLINICS}/{unknown}").status_code == 404
    resp = _invite(ops, unknown, Role.OWNER, "nowhere@example.test")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "REQ_NOT_FOUND"


def test_r4_a_clinic_gets_a_patient_code_prefix_derived_from_its_name_or_chosen_by_ops(
    world: World,
) -> None:
    ops = world.client_for(world.ops)

    derived = _post(ops, OPS_CLINICS, {"name": "Aarogya Family Clinic", "slug": "aarogya-family"})
    chosen = _post(
        ops,
        OPS_CLINICS,
        {"name": "Aarogya Two", "slug": "aarogya-two", "patient_code_prefix": "AR"},
    )

    assert derived.get_json()["patient_code_prefix"] == "AFC"
    assert chosen.get_json()["patient_code_prefix"] == "AR"
    assert world.client_for(world.a.owner).get(CLINIC).get_json()["patient_code_prefix"] == (
        world.a.clinic.patient_code_prefix
    )


@pytest.mark.parametrize("prefix", ["a", "abc", "ABCDE", "A1", "A B"])
def test_r4_a_bad_patient_code_prefix_is_refused(world: World, prefix: str) -> None:
    ops = world.client_for(world.ops)

    resp = _post(
        ops,
        OPS_CLINICS,
        {"name": "Prefix Test", "slug": "prefix-test", "patient_code_prefix": prefix},
    )

    assert resp.status_code == 422
    assert "patient_code_prefix" in {
        f["field"] for f in resp.get_json()["error"]["details"]["fields"]
    }
