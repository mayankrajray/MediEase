"""The owner's Team page API (M6a-P5; FR-ORG-07, FR-ORG-04, FR-AUTH-08).

Invitations to an email address are emailed by the worker with the secret made at send time
(decision 3A); phone-only ones return the link once. The ``send_staff_invite`` jobs the requests
enqueue are run by the real handler into an in-memory email port, so a test can follow the link.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.test import TestResponse

from mediease_api.adapters.email.console import ConsoleEmailAdapter
from mediease_api.adapters.security.refresh_secrets import Sha256RefreshTokenSecrets
from mediease_api.application.clinics.invite_email import SendStaffInvite
from mediease_api.domain.jobs.job import STAFF_INVITE_KIND, ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.ports.email import EmailFailed, EmailMessage
from tests.conftest import DEMO_PASSWORD, UowFactory, World
from tests.fakes import FakeClock

STAFF = "/api/v1/clinic/staff"
INVITES = "/api/v1/auth/invites"
PASSWORD = "a-new-staff-password"  # gitleaks:allow (synthetic test value)
SessionFactory = sessionmaker[Session]


class InviteMailbox:
    """Runs queued ``send_staff_invite`` jobs through the real handler and keeps what they sent."""

    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory
        self.port = ConsoleEmailAdapter()

    def _jobs(self) -> list[ClaimedJob]:
        with self._uow_factory() as uow:
            session = uow._require_open().session
            rows = session.execute(
                text(
                    "SELECT id, clinic_id, payload, max_attempts FROM jobs"
                    " WHERE kind = :k AND state = 'queued' ORDER BY created_at, id"
                ),
                {"k": STAFF_INVITE_KIND},
            ).all()
            session.execute(
                text("DELETE FROM jobs WHERE kind = :k AND state = 'queued'"),
                {"k": STAFF_INVITE_KIND},
            )
            uow.commit()
        return [
            ClaimedJob(
                id=row[0],
                kind=STAFF_INVITE_KIND,
                clinic_id=row[1],
                payload=row[2],
                attempts=1,
                max_attempts=row[3],
                request_id=None,
                locked_by="test",
            )
            for row in rows
        ]

    def handler(self, port: object | None = None) -> SendStaffInvite:
        return SendStaffInvite(
            uow=self._uow_factory(),
            clock=FakeClock(datetime.now(UTC)),
            secrets=Sha256RefreshTokenSecrets(),
            email=port or self.port,  # type: ignore[arg-type]
            public_base_url="https://app.example",
        )

    def payloads(self) -> list[dict[str, Any]]:
        with self._uow_factory() as uow:
            rows = uow._require_open().session.execute(
                text("SELECT payload FROM jobs WHERE kind = :k"), {"k": STAFF_INVITE_KIND}
            )
            return [dict(row[0]) for row in rows]

    def deliver(self) -> list[EmailMessage]:
        before = len(self.port.sent)
        for job in self._jobs():
            self.handler()(job)
        return self.port.sent[before:]


@pytest.fixture
def invites(uow_factory: UowFactory) -> InviteMailbox:
    return InviteMailbox(uow_factory)


def invite_token(message: EmailMessage) -> str:
    found = re.search(r"/invite/([A-Za-z0-9_\-]+)", message.text)
    assert found is not None, message.subject
    return found.group(1)


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def _invite(client: FlaskClient, **body: Any) -> TestResponse:
    return client.post(STAFF, json={"role": "FRONT_DESK", **body}, headers=_csrf(client))


def _resend(client: FlaskClient, membership_id: str) -> TestResponse:
    return client.post(f"{STAFF}/{membership_id}/resend", headers=_csrf(client))


def _member(client: FlaskClient, full_name: str) -> dict[str, Any]:
    staff = client.get(STAFF).get_json()["items"]
    return dict(next(m for m in staff if m["full_name"] == full_name))


def _accept(token: str, client: FlaskClient, password: str = PASSWORD) -> TestResponse:
    return client.post(f"{INVITES}/{token}/accept", json={"password": password})


def _digest_of(session_factory: SessionFactory, membership_id: str) -> str | None:
    with session_factory() as session:
        return session.execute(
            text("SELECT invite_token_hash FROM clinic_memberships WHERE id = :id"),
            {"id": membership_id},
        ).scalar_one()


def _events(session_factory: SessionFactory, action: str) -> list[dict[str, Any]]:
    with session_factory() as session:
        rows = session.execute(
            text("SELECT * FROM audit_events WHERE action = :action ORDER BY occurred_at"),
            {"action": action},
        )
        return [dict(row) for row in rows.mappings()]


# --- Emailed invitations -----------------------------------------------------------------------


def test_fr_org_07_an_emailed_invitation_stores_only_a_digest_and_works_once(
    world: World, session_factory: SessionFactory, invites: InviteMailbox
) -> None:
    owner = world.client_for(world.a.owner)

    invited = _invite(owner, full_name="New Desk", email="new.desk@example.test")

    assert invited.status_code == 201
    body = invited.get_json()
    assert (body["delivery"], body["accept_url"]) == ("email", None)
    assert body["email_masked"] == "n***@example.test"
    assert (body["status"], body["email"], body["invite_expires_at"]) == (
        "INVITED",
        "new.desk@example.test",
        None,
    )
    # Nothing usable exists before the worker sends, and the job holds IDs only.
    assert _digest_of(session_factory, body["membership_id"]) is None
    assert invites.payloads() == [{"membership_id": body["membership_id"]}]

    [message] = invites.deliver()
    assert message.to.value == "new.desk@example.test"
    assert message.subject == f"Join {world.a.clinic.name} on MediEase"
    assert "as front desk staff" in message.text
    token = invite_token(message)
    assert message.text.count(token) == 1
    digest = _digest_of(session_factory, body["membership_id"])
    assert digest == Sha256RefreshTokenSecrets().digest(token) != token
    assert _member(owner, "New Desk")["invite_expires_at"] is not None

    accepted = _accept(token, world.anonymous())
    assert accepted.status_code == 200
    replay = _accept(token, world.anonymous())
    assert replay.status_code == 410
    assert replay.get_json()["error"]["code"] == "CLN_INVITE_USED"
    assert _member(owner, "New Desk")["status"] == "ACTIVE"

    [event] = _events(session_factory, "staff.invited")
    assert event["metadata"] == {
        "target_user_id": body["user_id"],
        "role": "FRONT_DESK",
        "delivery": "email",
    }


def test_resend_retires_the_old_link_at_once(
    world: World, session_factory: SessionFactory, invites: InviteMailbox
) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _invite(owner, full_name="New Desk", email="new.desk@example.test").get_json()[
        "membership_id"
    ]
    first = invite_token(invites.deliver()[0])

    resent = _resend(owner, membership_id)

    assert resent.status_code == 200
    assert (resent.get_json()["delivery"], resent.get_json()["accept_url"]) == ("email", None)
    # The first link is dead before the new email is even sent.
    stale = world.anonymous().get(f"{INVITES}/{first}")
    assert stale.status_code == 404
    assert stale.get_json()["error"]["code"] == "CLN_INVITE_INVALID"

    second = invite_token(invites.deliver()[0])
    assert second != first
    assert _accept(second, world.anonymous()).status_code == 200
    events = _events(session_factory, "staff.invited")
    assert [e["metadata"].get("resent") for e in events] == [None, "true"]


def test_a_failed_send_retries_with_a_new_secret(
    world: World, session_factory: SessionFactory, invites: InviteMailbox
) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _invite(owner, full_name="New Desk", email="new.desk@example.test").get_json()[
        "membership_id"
    ]

    class Down:
        provider = "test"

        def send(self, message: EmailMessage) -> None:
            raise EmailFailed("unavailable", retryable=True)

    [job] = invites._jobs()
    with pytest.raises(JobFailure) as failure:
        invites.handler(Down())(job)
    assert failure.value.retryable
    unsent = _digest_of(session_factory, membership_id)
    assert unsent is not None

    invites.handler()(job)
    token = invite_token(invites.port.sent[-1])
    # The retry made another secret: the one in the email that never left is dead.
    assert _digest_of(session_factory, membership_id) not in (None, unsent)
    assert _accept(token, world.anonymous()).status_code == 200


def test_a_member_deactivated_before_the_send_gets_no_email(
    world: World, session_factory: SessionFactory, invites: InviteMailbox
) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _invite(owner, full_name="New Desk", email="new.desk@example.test").get_json()[
        "membership_id"
    ]
    owner.patch(f"{STAFF}/{membership_id}", json={"status": "DEACTIVATED"}, headers=_csrf(owner))

    assert invites.deliver() == []
    assert _digest_of(session_factory, membership_id) is None


# --- Phone-only invitations --------------------------------------------------------------------


def test_a_phone_only_invitation_returns_its_link_once(
    world: World, invites: InviteMailbox
) -> None:
    owner = world.client_for(world.a.owner)

    invited = _invite(owner, full_name="Phone Desk", phone="9000077001")

    assert invited.status_code == 201
    body = invited.get_json()
    assert (body["delivery"], body["email_masked"]) == ("link", None)
    assert body["accept_url"].startswith("http")
    assert body["phone_e164"] == "+919000077001"
    assert body["invite_expires_at"] is not None
    assert invites.payloads() == []
    # The list never repeats the link.
    assert "accept_url" not in _member(owner, "Phone Desk")

    again = _resend(owner, body["membership_id"])
    assert again.get_json()["delivery"] == "link"
    assert again.get_json()["accept_url"] != body["accept_url"]
    old = body["accept_url"].rsplit("/", 1)[1]
    assert world.anonymous().get(f"{INVITES}/{old}").status_code == 404


# --- Bringing someone back (decision 6A) -------------------------------------------------------


def test_fr_org_07_a_deactivated_member_is_invited_back_with_their_history(
    world: World, session_factory: SessionFactory, invites: InviteMailbox
) -> None:
    owner = world.client_for(world.a.owner)
    desk = _member(owner, "Alpha Front_Desk")
    owner.patch(
        f"{STAFF}/{desk['membership_id']}", json={"status": "DEACTIVATED"}, headers=_csrf(owner)
    )
    assert world.a.desk.email is not None

    back = _invite(
        owner, full_name="Alpha Front_Desk", role="DOCTOR", email=world.a.desk.email.value
    )

    assert back.status_code == 201
    body = back.get_json()
    assert (body["membership_id"], body["status"], body["role"]) == (
        desk["membership_id"],
        "INVITED",
        "DOCTOR",
    )
    [event] = _events(session_factory, "staff.reinvited")
    assert event["metadata"]["delivery"] == "email"
    assert event["metadata"]["role"] == "DOCTOR"

    # They already have a password, so they prove it to accept.
    token = invite_token(invites.deliver()[0])
    assert _accept(token, world.anonymous(), DEMO_PASSWORD).status_code == 200
    again = _member(owner, "Alpha Front_Desk")
    assert (again["membership_id"], again["status"], again["role"]) == (
        desk["membership_id"],
        "ACTIVE",
        "DOCTOR",
    )


def test_an_active_member_cannot_be_invited_again(world: World) -> None:
    owner = world.client_for(world.a.owner)
    assert world.a.desk.email is not None
    resp = _invite(owner, full_name="Alpha Front_Desk", email=world.a.desk.email.value)
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CLN_MEMBER_EXISTS"


def test_only_a_pending_invitation_can_be_resent(world: World) -> None:
    owner = world.client_for(world.a.owner)
    resp = _resend(owner, _member(owner, "Alpha Front_Desk")["membership_id"])
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CLN_INVALID_TRANSITION"


# --- The list ----------------------------------------------------------------------------------


def test_fr_org_07_the_list_tells_members_apart(world: World) -> None:
    owner = world.client_for(world.a.owner)

    doctor = _member(owner, "Alpha Doctor")
    desk = _member(owner, "Alpha Front_Desk")

    assert world.a.doctor_user.email is not None
    assert doctor["email"] == world.a.doctor_user.email.value
    assert doctor["has_doctor_profile"] is True
    assert desk["has_doctor_profile"] is False
    assert desk["invite_expires_at"] is None


# --- Limits and permissions --------------------------------------------------------------------


def test_an_owner_sends_at_most_10_invitations_an_hour(world: World) -> None:
    owner = world.client_for(world.a.owner)
    for n in range(10):
        ok = _invite(owner, full_name=f"Desk {n}", phone=f"90000880{n:02d}")
        assert ok.status_code == 201, ok.get_json()

    refused = _invite(owner, full_name="Desk 10", phone="9000088010")

    assert refused.status_code == 429
    assert refused.get_json()["error"]["code"] == "CLN_INVITE_RATE_LIMITED"
    assert 1 <= int(refused.headers["Retry-After"]) <= 3600
    # The limit is per clinic: another clinic's owner is unaffected.
    other = _invite(world.client_for(world.b.owner), full_name="Beta New", phone="9000088011")
    assert other.status_code == 201


def test_one_member_is_resent_at_most_3_times_an_hour(world: World) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _invite(owner, full_name="Phone Desk", phone="9000077002").get_json()[
        "membership_id"
    ]
    for _ in range(3):
        assert _resend(owner, membership_id).status_code == 200

    refused = _resend(owner, membership_id)
    assert refused.status_code == 429
    assert refused.get_json()["error"]["code"] == "CLN_INVITE_RATE_LIMITED"


@pytest.mark.parametrize("who", ["doctor_user", "desk"])
def test_only_owners_reach_the_team_routes(world: World, who: str) -> None:
    owner = world.client_for(world.a.owner)
    membership_id = _member(owner, "Alpha Doctor")["membership_id"]
    client = world.client_for(getattr(world.a, who))

    responses = [
        client.get(STAFF),
        _invite(client, full_name="X", email="x@example.test"),
        _resend(client, membership_id),
        client.patch(f"{STAFF}/{membership_id}", json={"role": "OWNER"}, headers=_csrf(client)),
    ]

    assert [r.status_code for r in responses] == [403, 403, 403, 403]
    assert {r.get_json()["error"]["code"] for r in responses} == {"PERM_DENIED"}
