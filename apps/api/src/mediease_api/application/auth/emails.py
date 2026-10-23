"""Account emails through the job queue (M6a-P4, ADR-0016 decision 4).

A request only enqueues ``send_auth_email`` with *which* email and *whose* account: the payload
holds no address and no secret. The worker re-reads the account, and for a link it then:

1. retires the account's earlier unused token of that purpose and stores a new token's digest,
   in one committed transaction;
2. sends the message with the token's value in the link.

A failed send retries with a new token, which retires the one in the unsent email. So no usable
secret is ever at rest, and an email outage never fails the request that asked for it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

import structlog

from mediease_api.application.auth import email_templates
from mediease_api.domain.identity.email_token import EmailToken, EmailTokenPurpose
from mediease_api.domain.identity.user import User
from mediease_api.domain.jobs.job import AUTH_EMAIL_KIND, ClaimedJob, NewJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.portal.account import PatientAccount, SignInMethod
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.email import EmailFailed, EmailMessage, EmailPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import RefreshTokenSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class AuthEmail(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    RESET_GOOGLE_ONLY = "reset_google_only"
    PASSWORD_CHANGED = "password_changed"


class Owner(StrEnum):
    STAFF = "staff"
    PATIENT = "patient"


_PURPOSE = {
    AuthEmail.VERIFY_EMAIL: EmailTokenPurpose.VERIFY_EMAIL,
    AuthEmail.RESET_PASSWORD: EmailTokenPurpose.RESET_PASSWORD,
}


def enqueue_auth_email(
    uow: UnitOfWork,
    *,
    ids: IdPort,
    email: AuthEmail,
    owner: Owner,
    account_id: UUID,
    now: datetime,
    request_id: str | None,
) -> None:
    """In the caller's transaction (the outbox)."""
    if email is AuthEmail.VERIFY_EMAIL and owner is not Owner.PATIENT:
        raise ValueError("only patient accounts verify their email in M6a")
    uow.jobs.enqueue(
        NewJob.create(
            id=ids.new_id(),
            kind=AUTH_EMAIL_KIND,
            now=now,
            payload={"email": email.value, "owner": owner.value, "account_id": str(account_id)},
            request_id=request_id,
        )
    )


class SendAuthEmail:
    """The ``send_auth_email`` job handler (run by the worker)."""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        secrets: RefreshTokenSecrets,
        email: EmailPort,
        public_base_url: str,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets
        self._email = email
        self._base = public_base_url.rstrip("/")

    def __call__(self, job: ClaimedJob) -> None:
        try:
            kind = AuthEmail(str(job.payload["email"]))
            owner = Owner(str(job.payload["owner"]))
            account_id = UUID(str(job.payload["account_id"]))
        except (KeyError, ValueError):
            raise JobFailure("JOB_HANDLER_ERROR", retryable=False) from None

        message = self._prepare(kind, owner, account_id)
        if message is None:
            return
        try:
            self._email.send(message)
        except EmailFailed as failure:
            logger.warning(
                "email.failed",
                email=kind.value,
                reason=failure.reason,
                retryable=failure.retryable,
                attempt=job.attempts,
            )
            raise JobFailure(
                f"EMAIL_{failure.reason.upper()}", retryable=failure.retryable
            ) from None
        logger.info("email.auth_sent", email=kind.value, owner=owner.value, to=message.to.masked())

    def _prepare(self, kind: AuthEmail, owner: Owner, account_id: UUID) -> EmailMessage | None:
        with self._uow as uow:
            now = self._clock.now()
            person = (
                uow.users.get(account_id)
                if owner is Owner.STAFF
                else uow.patient_accounts.get(account_id)
            )
            skip = _skip_reason(kind, person)
            if skip is not None:
                logger.info("email.skipped", email=kind.value, owner=owner.value, reason=skip)
                return None
            assert person is not None and person.email is not None
            address, name = person.email, person.full_name

            if kind is AuthEmail.PASSWORD_CHANGED:
                rendered = email_templates.password_changed(name)
            elif kind is AuthEmail.RESET_GOOGLE_ONLY:
                rendered = email_templates.reset_google_only(name, f"{self._base}/portal/sign-in")
            else:
                link = self._link(uow, kind, owner, account_id, address, now)
                uow.commit()
                rendered = (
                    email_templates.verify_email(name, link)
                    if kind is AuthEmail.VERIFY_EMAIL
                    else email_templates.reset_password(name, link)
                )
        return EmailMessage(
            to=address, subject=rendered.subject, text=rendered.text, html=rendered.html
        )

    def _link(
        self,
        uow: UnitOfWork,
        kind: AuthEmail,
        owner: Owner,
        account_id: UUID,
        address: EmailAddress,
        now: datetime,
    ) -> str:
        purpose = _PURPOSE[kind]
        staff = owner is Owner.STAFF
        uow.email_tokens.supersede_active(
            purpose=purpose, owner_id=account_id, staff=staff, now=now
        )
        value = self._secrets.generate()
        uow.email_tokens.add(
            EmailToken.issue(
                id=self._ids.new_id(),
                purpose=purpose,
                email=address,
                token_hash=self._secrets.digest(value),
                now=now,
                user_id=account_id if staff else None,
                patient_account_id=None if staff else account_id,
            )
        )
        if kind is AuthEmail.VERIFY_EMAIL:
            return f"{self._base}/portal/verify-email/{value}"
        prefix = "" if staff else "/portal"
        return f"{self._base}{prefix}/reset-password/{value}"


def _skip_reason(kind: AuthEmail, person: User | PatientAccount | None) -> str | None:
    """Why this email no longer applies at send time, if it does not (re-read, like messaging)."""
    if person is None:
        return "account_gone"
    if person.email is None:
        return "no_email"
    if isinstance(person, User):
        if not person.is_active or person.is_platform_ops:
            return "not_eligible"
        if kind is AuthEmail.RESET_PASSWORD and person.password_hash is None:
            return "no_password"
        return None
    if not person.is_active:
        return "not_eligible"
    if kind is AuthEmail.VERIFY_EMAIL and person.is_email_verified:
        return "already_verified"
    if kind is AuthEmail.RESET_PASSWORD and person.sign_in_method is not SignInMethod.PASSWORD:
        return "no_password"
    return None
