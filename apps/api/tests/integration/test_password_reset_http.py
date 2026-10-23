"""Password reset and email verification end to end (M6a-P4; FR-AUTH-05, 08; ADR-0016).

The HTTP routes and use cases run against PostgreSQL; the ``send_auth_email`` jobs they enqueue
are then run by the real handler into an in-memory email port, so a test can follow a link.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from flask.testing import FlaskClient
from sqlalchemy import text

from mediease_api.adapters.email.console import ConsoleEmailAdapter
from mediease_api.adapters.security.refresh_secrets import Sha256RefreshTokenSecrets
from mediease_api.application.auth.emails import SendAuthEmail
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.jobs.job import AUTH_EMAIL_KIND, ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.ports.email import EmailFailed, EmailMessage
from tests.conftest import DEMO_PASSWORD, UowFactory, seed_staff
from tests.fakes import FakeClock, FakeIds
from tests.integration.test_google_http import google
from tests.integration.test_portal_http import EMAIL, PASSWORD, portal_csrf, sign_up

STAFF_RESET = "/api/v1/auth/password-reset"
STAFF_COMPLETE = "/api/v1/auth/password-reset/complete"
PORTAL_RESET = "/api/v1/portal/auth/password-reset"
PORTAL_COMPLETE = "/api/v1/portal/auth/password-reset/complete"
VERIFY = "/api/v1/portal/auth/verify-email"
RESEND = "/api/v1/portal/auth/verify-email/resend"
NEW_PASSWORD = "a-brand-new-synthetic-pass"  # gitleaks:allow (synthetic test value)


class Mailbox:
    """Runs queued ``send_auth_email`` jobs through the real handler and keeps what they sent."""

    def __init__(self, uow_factory: UowFactory) -> None:
        self._uow_factory = uow_factory
        self.port = ConsoleEmailAdapter()

    def _jobs(self) -> list[ClaimedJob]:
        with self._uow_factory() as uow:
            session = uow._require_open().session
            rows = session.execute(
                text(
                    "SELECT id, payload, max_attempts FROM jobs"
                    " WHERE kind = :k AND state = 'queued'"
                    " ORDER BY created_at, id"
                ),
                {"k": AUTH_EMAIL_KIND},
            ).all()
            session.execute(
                text("DELETE FROM jobs WHERE kind = :k AND state = 'queued'"),
                {"k": AUTH_EMAIL_KIND},
            )
            uow.commit()
        return [
            ClaimedJob(
                id=row[0],
                kind=AUTH_EMAIL_KIND,
                clinic_id=None,
                payload=row[1],
                attempts=1,
                max_attempts=row[2],
                request_id=None,
                locked_by="test",
            )
            for row in rows
        ]

    def handler(self, port: object | None = None) -> SendAuthEmail:
        return SendAuthEmail(
            uow=self._uow_factory(),
            clock=FakeClock(datetime.now(UTC)),
            ids=FakeIds(),
            secrets=Sha256RefreshTokenSecrets(),
            email=port or self.port,  # type: ignore[arg-type]
            public_base_url="https://app.example",
        )

    def deliver(self) -> list[EmailMessage]:
        before = len(self.port.sent)
        for job in self._jobs():
            self.handler()(job)
        return self.port.sent[before:]

    def queued(self) -> int:
        with self._uow_factory() as uow:
            return int(
                uow._require_open()
                .session.execute(
                    text("SELECT count(*) FROM jobs WHERE kind = :k"), {"k": AUTH_EMAIL_KIND}
                )
                .scalar_one()
            )


@pytest.fixture
def mailbox(uow_factory: UowFactory) -> Mailbox:
    return Mailbox(uow_factory)


def _token(message: EmailMessage, path: str) -> str:
    found = re.search(rf"{re.escape(path)}/([A-Za-z0-9_\-]+)", message.text)
    assert found is not None, message.subject
    return found.group(1)


def _sign_in_staff(client: FlaskClient, email: str, password: str = DEMO_PASSWORD) -> int:
    return client.post(
        "/api/v1/auth/sign-in", json={"identifier": email, "password": password}
    ).status_code


# --- Staff -------------------------------------------------------------------------------------


def test_fr_auth_05_known_and_unknown_addresses_get_the_same_answer(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    user = seed_staff(uow_factory, role=Role.DOCTOR)
    assert user.email is not None
    known = db_client.post(STAFF_RESET, json={"email": user.email.value})
    unknown = db_client.post(STAFF_RESET, json={"email": "nobody@example.test"})
    assert known.status_code == unknown.status_code == 202
    assert known.get_json() == unknown.get_json() == {"accepted": True}
    assert mailbox.queued() == 1  # only the real account gets an email

    sent = mailbox.deliver()
    assert [m.to.value for m in sent] == [user.email.value]
    assert sent[0].subject == "Reset your MediEase password"
    with uow_factory() as uow:
        session = uow._require_open().session
        actions = session.execute(text("SELECT action FROM audit_events")).scalars().all()
        stored = session.execute(text("SELECT token_hash FROM email_tokens")).scalars().all()
    assert actions == ["auth.password_reset_requested"]
    assert _token(sent[0], "/reset-password") not in stored  # only the digest is stored


def test_fr_auth_05_ops_and_invited_users_get_no_link(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    ops = seed_staff(uow_factory, is_platform_ops=True)
    invited = seed_staff(uow_factory, password=None)
    for user in (ops, invited):
        assert user.email is not None
        assert db_client.post(STAFF_RESET, json={"email": user.email.value}).status_code == 202
    assert mailbox.queued() == 0


def test_fr_auth_05_a_reset_changes_the_password_and_ends_every_session(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    email = user.email.value
    signed_in = db_client.application.test_client()
    assert _sign_in_staff(signed_in, email) == 200

    db_client.post(STAFF_RESET, json={"email": email})
    token = _token(mailbox.deliver()[0], "/reset-password")
    done = db_client.post(STAFF_COMPLETE, json={"token": token, "password": NEW_PASSWORD})
    assert done.status_code == 204

    assert signed_in.get("/api/v1/me").status_code == 401  # the old session is over
    fresh = db_client.application.test_client()
    assert _sign_in_staff(fresh, email) == 401
    assert _sign_in_staff(fresh, email, NEW_PASSWORD) == 200

    changed = mailbox.deliver()
    assert [m.subject for m in changed] == ["Your MediEase password was changed"]
    again = db_client.post(STAFF_COMPLETE, json={"token": token, "password": NEW_PASSWORD})
    assert again.status_code == 404
    assert again.get_json()["error"]["code"] == "AUTH_TOKEN_INVALID"


def test_adr_0016_an_older_link_is_superseded_and_an_expired_one_refused(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    db_client.post(STAFF_RESET, json={"email": user.email.value})
    first = _token(mailbox.deliver()[0], "/reset-password")
    db_client.post(STAFF_RESET, json={"email": user.email.value})
    second = _token(mailbox.deliver()[0], "/reset-password")

    old = db_client.post(STAFF_COMPLETE, json={"token": first, "password": NEW_PASSWORD})
    assert old.status_code == 404

    with uow_factory() as uow:
        uow._require_open().session.execute(
            text("UPDATE email_tokens SET expires_at = now() - interval '1 minute'")
        )
        uow.commit()
    expired = db_client.post(STAFF_COMPLETE, json={"token": second, "password": NEW_PASSWORD})
    assert expired.status_code == 410
    assert expired.get_json()["error"]["code"] == "AUTH_TOKEN_EXPIRED"


def test_a_weak_new_password_is_refused_and_the_link_stays_usable(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    db_client.post(STAFF_RESET, json={"email": user.email.value})
    token = _token(mailbox.deliver()[0], "/reset-password")
    weak = db_client.post(STAFF_COMPLETE, json={"token": token, "password": "short"})
    assert weak.status_code == 422
    ok = db_client.post(STAFF_COMPLETE, json={"token": token, "password": NEW_PASSWORD})
    assert ok.status_code == 204


def test_adr_0016_three_emails_an_hour_per_account_silently(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    codes = [
        db_client.post(STAFF_RESET, json={"email": user.email.value}).status_code for _ in range(4)
    ]
    assert codes == [202] * 4
    assert mailbox.queued() == 3


def test_a_staff_link_does_not_work_on_the_portal(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    db_client.post(STAFF_RESET, json={"email": user.email.value})
    token = _token(mailbox.deliver()[0], "/reset-password")
    wrong = db_client.post(PORTAL_COMPLETE, json={"token": token, "password": NEW_PASSWORD})
    assert wrong.status_code == 404


# --- Patients ----------------------------------------------------------------------------------


def test_fr_auth_08_sign_up_sends_a_verification_link_that_verifies_once(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    sign_up(db_client)
    sent = mailbox.deliver()
    assert [(m.to.value, m.subject) for m in sent] == [(EMAIL, "Confirm your email for MediEase")]
    token = _token(sent[0], "/portal/verify-email")

    assert db_client.post(VERIFY, json={"token": token}).status_code == 204
    assert db_client.get("/api/v1/portal/me").get_json()["account"]["email_verified"] is True
    assert db_client.post(VERIFY, json={"token": token}).status_code == 404
    with uow_factory() as uow:
        actions = (
            uow._require_open()
            .session.execute(text("SELECT action FROM audit_events ORDER BY occurred_at, id"))
            .scalars()
            .all()
        )
    assert "patient.email_verified" in actions

    # Nothing left to verify: a resend says so and sends nothing.
    resent = db_client.post(RESEND, headers=portal_csrf(db_client))
    assert resent.status_code == 202
    assert resent.get_json() == {"accepted": False}
    assert mailbox.queued() == 0


def test_fr_auth_08_resend_sends_a_new_link_and_retires_the_old_one(
    db_client: FlaskClient, mailbox: Mailbox
) -> None:
    sign_up(db_client)
    first = _token(mailbox.deliver()[0], "/portal/verify-email")
    resent = db_client.post(RESEND, headers=portal_csrf(db_client))
    assert resent.get_json() == {"accepted": True}
    second = _token(mailbox.deliver()[0], "/portal/verify-email")
    assert db_client.post(VERIFY, json={"token": first}).status_code == 404
    assert db_client.post(VERIFY, json={"token": second}).status_code == 204


def test_resend_is_limited_to_three_an_hour(db_client: FlaskClient) -> None:
    sign_up(db_client)
    codes = [db_client.post(RESEND, headers=portal_csrf(db_client)).status_code for _ in range(4)]
    assert codes == [202, 202, 202, 429]


def test_fr_auth_05_a_patient_reset_verifies_the_email_and_ends_portal_sessions(
    db_client: FlaskClient, mailbox: Mailbox
) -> None:
    sign_up(db_client)
    mailbox.deliver()  # the verification email, not used
    other = db_client.application.test_client()
    assert other.post(PORTAL_RESET, json={"email": EMAIL}).status_code == 202
    token = _token(mailbox.deliver()[0], "/portal/reset-password")
    done = other.post(PORTAL_COMPLETE, json={"token": token, "password": NEW_PASSWORD})
    assert done.status_code == 204

    assert db_client.get("/api/v1/portal/me").status_code == 401
    signed_in = other.post(
        "/api/v1/portal/auth/sign-in", json={"email": EMAIL, "password": NEW_PASSWORD}
    )
    assert signed_in.status_code == 200
    assert signed_in.get_json()["account"]["email_verified"] is True
    old = db_client.application.test_client().post(
        "/api/v1/portal/auth/sign-in", json={"email": EMAIL, "password": PASSWORD}
    )
    assert old.status_code == 401


def test_adr_0016_a_google_only_patient_is_told_to_use_google(
    db_client: FlaskClient, mailbox: Mailbox
) -> None:
    google(db_client, "patient", "ravi@example.test")
    assert db_client.post(PORTAL_RESET, json={"email": "ravi@example.test"}).status_code == 202
    sent = mailbox.deliver()
    assert [m.subject for m in sent] == ["Your MediEase account signs in with Google"]
    assert "/reset-password/" not in sent[0].text


# --- The send job ------------------------------------------------------------------------------


class Refusing:
    provider = "test"

    def __init__(self, retryable: bool) -> None:
        self.retryable = retryable

    def send(self, message: EmailMessage) -> None:
        raise EmailFailed("smtp_unreachable", retryable=self.retryable)


def test_adr_0016_a_failed_send_retries_with_a_new_token_that_retires_the_unsent_one(
    db_client: FlaskClient, uow_factory: UowFactory, mailbox: Mailbox
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    db_client.post(STAFF_RESET, json={"email": user.email.value})
    [job] = mailbox._jobs()
    with pytest.raises(JobFailure) as failure:
        mailbox.handler(Refusing(retryable=True))(job)
    assert failure.value.code == "EMAIL_SMTP_UNREACHABLE"
    assert failure.value.retryable

    mailbox.handler()(job)  # the retry
    with uow_factory() as uow:
        rows = (
            uow._require_open()
            .session.execute(
                text("SELECT superseded_at IS NOT NULL FROM email_tokens ORDER BY created_at, id")
            )
            .scalars()
            .all()
        )
    assert rows == [True, False]
