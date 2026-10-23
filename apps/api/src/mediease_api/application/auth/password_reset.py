"""Password reset for staff and patients, and email verification (M6a-P4; FR-AUTH-05, 08).

ADR-0016 decisions 5-7.

- **Request** answers the same way whether or not the address has an account: the caller cannot
  tell. Only for an eligible account is an email enqueued (and audited): a staff user who is
  active, not platform ops and has a password; a patient password account; or, for a
  Google-only patient, a "you sign in with Google" notice instead of a link. Rate limited per
  caller (an error) and per account (silently, so the limit itself reveals nothing).
- **Complete** applies the password policy, clears the lockout, ends **every** session of the
  account and sends a "password changed" email. It does not sign the person in. For a patient
  it also verifies the email, which the link just proved.
- **Verify** marks a patient password account's email as proved. **Resend** sends a new link,
  at most three an hour.
"""

from __future__ import annotations

from datetime import datetime

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.auth._session import may_hold_session
from mediease_api.application.auth.emails import AuthEmail, Owner, enqueue_auth_email
from mediease_api.application.auth.errors import AuthRateLimited
from mediease_api.application.auth.rate_limit import enforce_rate_limit
from mediease_api.application.context import Actor, RequestInfo
from mediease_api.application.portal.sessions import record_patient_event
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.email_token import (
    EmailToken,
    EmailTokenPurpose,
    TokenInvalid,
)
from mediease_api.domain.identity.password import validate_password
from mediease_api.domain.portal.account import SignInMethod
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import PasswordHasher, RefreshTokenSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

REQUESTS_PER_CALLER_PER_MINUTE = 5
COMPLETIONS_PER_CALLER_PER_MINUTE = 10
EMAILS_PER_ACCOUNT_PER_HOUR = 3


def _account_hits(uow: UnitOfWork, bucket: str, now: datetime) -> int:
    """One more email for this account in the current hour (the M4-P5 table, hour windows)."""
    return uow.rate_limits.hit(bucket, window_start=now.replace(minute=0, second=0, microsecond=0))


class RequestPasswordReset:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, raw_email: str, *, owner: Owner, info: RequestInfo) -> None:
        enforce_rate_limit(
            self._uow,
            self._clock,
            info,
            bucket=f"password-reset-{owner.value}",
            limit=REQUESTS_PER_CALLER_PER_MINUTE,
        )
        email = EmailAddress.parse(raw_email)
        with self._uow as uow:
            now = self._clock.now()
            if owner is Owner.STAFF:
                sent = self._staff(uow, email, info, now)
            else:
                sent = self._patient(uow, email, info, now)
            uow.commit()
        # The same event whatever happened; only `sent` (never returned) says which.
        logger.info("auth.password_reset_requested", owner=owner.value, sent=sent)

    def _staff(
        self, uow: UnitOfWork, email: EmailAddress, info: RequestInfo, now: datetime
    ) -> bool:
        user = uow.users.get_by_email(email)
        if user is None or user.is_platform_ops or user.password_hash is None:
            return False
        if not may_hold_session(user, list(uow.clinic_access.list_active_for_user(user.id))):
            return False
        if _account_hits(uow, f"reset-staff:{user.id}", now) > EMAILS_PER_ACCOUNT_PER_HOUR:
            return False
        enqueue_auth_email(
            uow,
            ids=self._ids,
            email=AuthEmail.RESET_PASSWORD,
            owner=Owner.STAFF,
            account_id=user.id,
            now=now,
            request_id=info.request_id,
        )
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=AuditAction.AUTH_PASSWORD_RESET_REQUESTED,
            actor=Actor.for_user(user, info),
            now=now,
        )
        return True

    def _patient(
        self, uow: UnitOfWork, email: EmailAddress, info: RequestInfo, now: datetime
    ) -> bool:
        account = uow.patient_accounts.get_password_account(email)
        kind = AuthEmail.RESET_PASSWORD
        if account is None:
            account = uow.patient_accounts.find_google_account(email)
            kind = AuthEmail.RESET_GOOGLE_ONLY
        if account is None or not account.is_active:
            return False
        if _account_hits(uow, f"reset-patient:{account.id}", now) > EMAILS_PER_ACCOUNT_PER_HOUR:
            return False
        enqueue_auth_email(
            uow,
            ids=self._ids,
            email=kind,
            owner=Owner.PATIENT,
            account_id=account.id,
            now=now,
            request_id=info.request_id,
        )
        record_patient_event(
            uow,
            self._ids,
            action=AuditAction.AUTH_PASSWORD_RESET_REQUESTED,
            account_id=account.id,
            info=info,
            now=now,
            email=kind.value,
        )
        return True


class CompletePasswordReset:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        hasher: PasswordHasher,
        secrets: RefreshTokenSecrets,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._hasher = hasher
        self._secrets = secrets

    def execute(self, raw_token: str, password: str, *, owner: Owner, info: RequestInfo) -> None:
        enforce_rate_limit(
            self._uow,
            self._clock,
            info,
            bucket="password-reset-complete",
            limit=COMPLETIONS_PER_CALLER_PER_MINUTE,
        )
        validate_password(password)
        password_hash = self._hasher.hash(password)
        with self._uow as uow:
            now = self._clock.now()
            token = _token(uow, self._secrets, raw_token)
            if token.is_for_staff is not (owner is Owner.STAFF):
                raise TokenInvalid()
            if owner is Owner.STAFF:
                revoked = self._staff(uow, token, password_hash, info, now)
            else:
                revoked = self._patient(uow, token, password_hash, info, now)
            token.use(now=now)
            uow.email_tokens.update(token)
            account_id = token.user_id or token.patient_account_id
            assert account_id is not None
            enqueue_auth_email(
                uow,
                ids=self._ids,
                email=AuthEmail.PASSWORD_CHANGED,
                owner=owner,
                account_id=account_id,
                now=now,
                request_id=info.request_id,
            )
            uow.commit()
        logger.info("auth.password_reset", owner=owner.value, revoked_sessions=revoked)

    def _staff(
        self,
        uow: UnitOfWork,
        token: EmailToken,
        password_hash: str,
        info: RequestInfo,
        now: datetime,
    ) -> int:
        assert token.user_id is not None
        user = uow.users.get(token.user_id, for_update=True)
        if user is None or user.email is None or not user.is_active or user.is_platform_ops:
            raise TokenInvalid()
        token.check_usable(purpose=EmailTokenPurpose.RESET_PASSWORD, email=user.email, now=now)
        user.set_password_hash(password_hash, now=now)
        user.clear_lockout(now=now)
        uow.users.update(user)
        revoked = uow.refresh_tokens.revoke_all_for_owner(user.id, now=now)
        record_event(
            uow,
            event_id=self._ids.new_id(),
            action=AuditAction.AUTH_PASSWORD_RESET,
            actor=Actor.for_user(user, info),
            now=now,
            metadata={"revoked_count": str(revoked)},
        )
        return revoked

    def _patient(
        self,
        uow: UnitOfWork,
        token: EmailToken,
        password_hash: str,
        info: RequestInfo,
        now: datetime,
    ) -> int:
        assert token.patient_account_id is not None
        account = uow.patient_accounts.get(token.patient_account_id, for_update=True)
        if (
            account is None
            or not account.is_active
            or account.sign_in_method is not SignInMethod.PASSWORD
        ):
            raise TokenInvalid()
        token.check_usable(purpose=EmailTokenPurpose.RESET_PASSWORD, email=account.email, now=now)
        account.set_password_hash(password_hash, now=now)
        account.clear_lockout(now=now)
        account.verify_email(now=now)  # the link just proved the address
        uow.patient_accounts.update(account)
        revoked = uow.patient_refresh_tokens.revoke_all_for_owner(account.id, now=now)
        record_patient_event(
            uow,
            self._ids,
            action=AuditAction.PATIENT_PASSWORD_RESET,
            account_id=account.id,
            info=info,
            now=now,
            revoked_count=str(revoked),
        )
        return revoked


class VerifyEmail:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: RefreshTokenSecrets
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def execute(self, raw_token: str, info: RequestInfo) -> None:
        enforce_rate_limit(
            self._uow,
            self._clock,
            info,
            bucket="verify-email",
            limit=COMPLETIONS_PER_CALLER_PER_MINUTE,
        )
        with self._uow as uow:
            now = self._clock.now()
            token = _token(uow, self._secrets, raw_token)
            if token.patient_account_id is None:
                raise TokenInvalid()
            account = uow.patient_accounts.get(token.patient_account_id, for_update=True)
            if account is None or not account.is_active:
                raise TokenInvalid()
            token.check_usable(purpose=EmailTokenPurpose.VERIFY_EMAIL, email=account.email, now=now)
            token.use(now=now)
            uow.email_tokens.update(token)
            if account.verify_email(now=now):
                uow.patient_accounts.update(account)
                record_patient_event(
                    uow,
                    self._ids,
                    action=AuditAction.PATIENT_EMAIL_VERIFIED,
                    account_id=account.id,
                    info=info,
                    now=now,
                )
            uow.commit()
        logger.info("portal.email_verified", account_id=str(account.id))


class ResendVerification:
    """A new verification link for the signed-in patient, at most three an hour."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, principal: PatientPrincipal, info: RequestInfo) -> bool:
        account = principal.account
        if account.is_email_verified or account.sign_in_method is not SignInMethod.PASSWORD:
            return False
        with self._uow as uow:
            now = self._clock.now()
            hits = _account_hits(uow, f"verify-patient:{account.id}", now)
            if hits > EMAILS_PER_ACCOUNT_PER_HOUR:
                uow.commit()
                retry = int(
                    (now.replace(minute=0, second=0, microsecond=0) - now).total_seconds() + 3600
                )
                raise AuthRateLimited(max(1, retry))
            enqueue_auth_email(
                uow,
                ids=self._ids,
                email=AuthEmail.VERIFY_EMAIL,
                owner=Owner.PATIENT,
                account_id=account.id,
                now=now,
                request_id=info.request_id,
            )
            uow.commit()
        logger.info("portal.verification_resent", account_id=str(account.id))
        return True


def _token(uow: UnitOfWork, secrets: RefreshTokenSecrets, raw: str) -> EmailToken:
    if not raw or len(raw) > 128:
        raise TokenInvalid()
    token = uow.email_tokens.get_by_hash(secrets.digest(raw), for_update=True)
    if token is None:
        logger.info("auth.email_token_rejected", reason="unknown")
        raise TokenInvalid()
    return token
