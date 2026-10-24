"""Portal sign-up, sign-in, refresh, sign-out and per-request authentication (M6a-P3).

The staff rules, applied to ``patient_accounts`` (ADR-0015 decisions 1, 2, 5, 7):

- **Sign-up** takes a name, an email and a password (the staff policy, 12 characters minimum),
  creates a ``PASSWORD`` account with an unverified email and signs the person in. An email that
  already has a password account is refused with ``PRT_EMAIL_TAKEN`` (accepted, rate limited).
- **Sign-in** is email and password, Argon2id, five failures lock for 15 minutes. Unknown
  addresses and Google-only accounts cost one hash too and get the same generic error.
- **Refresh** rotates within the family; presenting a rotated token revokes the family.
- **Authentication** re-reads the session and the account on every request, like staff.

Sign-up and sign-in are rate limited per caller before any hashing.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from mediease_api.application.auth.emails import AuthEmail, Owner, enqueue_auth_email
from mediease_api.application.auth.errors import (
    AccountLocked,
    RefreshTokenReused,
    SessionExpired,
)
from mediease_api.application.auth.rate_limit import (
    SIGN_IN_PER_MINUTE,
    SIGN_UP_PER_MINUTE,
    enforce_rate_limit,
)
from mediease_api.application.context import RequestInfo
from mediease_api.application.portal.errors import (
    PortalAccountDisabled,
    PortalInvalidCredentials,
)
from mediease_api.application.portal.sessions import PatientSessionIssuer, record_patient_event
from mediease_api.application.portal.views import (
    PatientAccountView,
    PatientPrincipal,
    PatientSessionResult,
)
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.password import validate_password
from mediease_api.domain.identity.session import RefreshTokenState
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.account import (
    MAX_NAME_LENGTH,
    EmailTaken,
    PatientAccount,
    SignInMethod,
)
from mediease_api.domain.portal.medicines import SlotTimes
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.text import required_text
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import (
    AccessTokenIssuer,
    InvalidAccessToken,
    PasswordHasher,
    RefreshTokenSecrets,
)
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SignUpCommand:
    full_name: str
    email: str
    password: str
    # M6b-P2: the language the sign-up page was in (decision 2A).
    language: Language = Language.EN

    def __repr__(self) -> str:
        return "SignUpCommand(<redacted>)"


@dataclass(frozen=True, slots=True)
class PortalSignInCommand:
    email: str
    password: str

    def __repr__(self) -> str:
        return "PortalSignInCommand(<redacted>)"


class SignUpPatient:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        hasher: PasswordHasher,
        sessions: PatientSessionIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._hasher = hasher
        self._sessions = sessions

    def execute(self, cmd: SignUpCommand, info: RequestInfo) -> PatientSessionResult:
        enforce_rate_limit(
            self._uow, self._clock, info, bucket="portal-sign-up", limit=SIGN_UP_PER_MINUTE
        )
        email = EmailAddress.parse(cmd.email)
        password = validate_password(cmd.password)
        # Validate the name before paying for a hash.
        required_text(cmd.full_name, "full_name", max_length=MAX_NAME_LENGTH)
        password_hash = self._hasher.hash(password)
        with self._uow as uow:
            now = self._clock.now()
            if uow.patient_accounts.get_password_account(email) is not None:
                logger.info("portal.sign_up_refused", reason="email_taken")
                raise EmailTaken()
            account = PatientAccount.with_password(
                id=self._ids.new_id(),
                full_name=cmd.full_name,
                email=email,
                password_hash=password_hash,
                now=now,
                language=cmd.language,
            )
            account.record_successful_sign_in(now=now)
            uow.patient_accounts.add(account)  # EmailTaken if a parallel sign-up won
            session_id, result = self._sessions.start(uow, account, now=now)
            # M6a-P4: the verification email, sent by the worker (ADR-0016).
            enqueue_auth_email(
                uow,
                ids=self._ids,
                email=AuthEmail.VERIFY_EMAIL,
                owner=Owner.PATIENT,
                account_id=account.id,
                now=now,
                request_id=info.request_id,
            )
            method = SignInMethod.PASSWORD.value
            record_patient_event(
                uow,
                self._ids,
                action=AuditAction.PATIENT_ACCOUNT_CREATED,
                account_id=account.id,
                info=info,
                now=now,
                method=method,
            )
            record_patient_event(
                uow,
                self._ids,
                action=AuditAction.PATIENT_SIGNED_IN,
                account_id=account.id,
                info=info,
                now=now,
                method=method,
                session_id=str(session_id),
            )
            uow.commit()
        logger.info("portal.signed_up", account_id=str(account.id), session_id=str(session_id))
        return result


class SignInPatient:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        hasher: PasswordHasher,
        sessions: PatientSessionIssuer,
        dummy_password_hash: str,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._hasher = hasher
        self._sessions = sessions
        self._dummy_hash = dummy_password_hash

    def execute(self, cmd: PortalSignInCommand, info: RequestInfo) -> PatientSessionResult:
        enforce_rate_limit(
            self._uow, self._clock, info, bucket="portal-sign-in", limit=SIGN_IN_PER_MINUTE
        )
        email = _parse_email(cmd.email)
        with self._uow as uow:
            now = self._clock.now()
            account = (
                uow.patient_accounts.get_password_account(email, for_update=True)
                if email is not None
                else None
            )
            if account is None or account.password_hash is None:
                self._hasher.verify(self._dummy_hash, cmd.password)
                logger.info("portal.sign_in_failed", reason="unknown_email")
                raise PortalInvalidCredentials()

            if account.is_locked(now):
                self._hasher.verify(self._dummy_hash, cmd.password)
                assert account.locked_until is not None
                retry_after = max(1, int((account.locked_until - now).total_seconds()))
                logger.info("portal.sign_in_failed", reason="locked", account_id=str(account.id))
                raise AccountLocked(retry_after)

            if not self._hasher.verify(account.password_hash, cmd.password):
                locked_now = account.record_failed_sign_in(now=now)
                uow.patient_accounts.update(account)
                record_patient_event(
                    uow,
                    self._ids,
                    action=AuditAction.PATIENT_SIGN_IN_FAILED,
                    account_id=account.id,
                    info=info,
                    now=now,
                    reason="wrong_password",
                    locked=str(locked_now).lower(),
                )
                uow.commit()
                logger.info(
                    "portal.sign_in_failed", reason="wrong_password", account_id=str(account.id)
                )
                raise PortalInvalidCredentials()

            if not account.is_active:
                logger.info("portal.sign_in_failed", reason="disabled", account_id=str(account.id))
                raise PortalAccountDisabled()

            if self._hasher.needs_rehash(account.password_hash):
                account.set_password_hash(self._hasher.hash(cmd.password), now=now)
            account.record_successful_sign_in(now=now)
            uow.patient_accounts.update(account)
            session_id, result = self._sessions.start(uow, account, now=now)
            record_patient_event(
                uow,
                self._ids,
                action=AuditAction.PATIENT_SIGNED_IN,
                account_id=account.id,
                info=info,
                now=now,
                method=SignInMethod.PASSWORD.value,
                session_id=str(session_id),
            )
            uow.commit()
        logger.info("portal.signed_in", account_id=str(account.id), session_id=str(session_id))
        return result


class RefreshPatientSession:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        secrets: RefreshTokenSecrets,
        sessions: PatientSessionIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets
        self._sessions = sessions

    def execute(self, refresh_token: str, info: RequestInfo) -> PatientSessionResult:
        digest = self._secrets.digest(refresh_token)
        with self._uow as uow:
            now = self._clock.now()
            token = uow.patient_refresh_tokens.get_by_hash(digest, for_update=True)
            if token is None:
                logger.info("portal.refresh_failed", reason="unknown")
                raise SessionExpired()

            state = token.state(now)
            if state is RefreshTokenState.ROTATED:
                revoked = uow.patient_refresh_tokens.revoke_family(token.family_id, now=now)
                record_patient_event(
                    uow,
                    self._ids,
                    action=AuditAction.PATIENT_REFRESH_REUSED,
                    account_id=token.user_id,
                    info=info,
                    now=now,
                    session_id=str(token.family_id),
                    revoked_count=str(revoked),
                )
                uow.commit()
                logger.warning(
                    "portal.refresh_reused",
                    account_id=str(token.user_id),
                    session_id=str(token.family_id),
                    revoked_count=revoked,
                )
                raise RefreshTokenReused()
            if state is not RefreshTokenState.ACTIVE:
                logger.info("portal.refresh_failed", reason=state.value.lower())
                raise SessionExpired()

            account = uow.patient_accounts.get(token.user_id)
            if account is None or not account.is_active:
                uow.patient_refresh_tokens.revoke_family(token.family_id, now=now)
                uow.commit()
                logger.info("portal.refresh_failed", reason="account_disabled")
                raise PortalAccountDisabled()

            successor, tokens = self._sessions.issue(
                uow, account_id=account.id, family_id=token.family_id, now=now
            )
            token.mark_replaced(successor.id, now=now)
            uow.patient_refresh_tokens.update(token)
            uow.commit()

        logger.info("portal.refreshed", account_id=str(account.id), session_id=str(token.family_id))
        return PatientSessionResult(PatientAccountView.of(account), tokens)


class SignOutPatient:
    """Idempotent: no token, or an unknown one, simply ends nothing."""

    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: RefreshTokenSecrets
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def execute(self, refresh_token: str | None, info: RequestInfo) -> None:
        if not refresh_token:
            return
        digest = self._secrets.digest(refresh_token)
        with self._uow as uow:
            now = self._clock.now()
            token = uow.patient_refresh_tokens.get_by_hash(digest)
            if token is None:
                return
            revoked = uow.patient_refresh_tokens.revoke_family(token.family_id, now=now)
            record_patient_event(
                uow,
                self._ids,
                action=AuditAction.PATIENT_SIGNED_OUT,
                account_id=token.user_id,
                info=info,
                now=now,
                session_id=str(token.family_id),
                revoked_count=str(revoked),
            )
            uow.commit()
        logger.info(
            "portal.signed_out", account_id=str(token.user_id), session_id=str(token.family_id)
        )


class AuthenticatePatient:
    """Every portal request: the token (portal audience), a live family, an active account."""

    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, access_tokens: AccessTokenIssuer
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._access_tokens = access_tokens

    def execute(self, access_token: str | None) -> PatientPrincipal:
        if not access_token:
            raise SessionExpired()
        now = self._clock.now()
        try:
            claims = self._access_tokens.verify(access_token, now=now)
        except InvalidAccessToken:
            logger.info("portal.rejected", reason="invalid_token")
            raise SessionExpired() from None

        with self._uow as uow:
            if not uow.patient_refresh_tokens.is_family_live(claims.session_id, now=now):
                logger.info("portal.rejected", reason="session_ended")
                raise SessionExpired()
            account = uow.patient_accounts.get(claims.user_id)
            if account is None or not account.is_active:
                logger.info("portal.rejected", reason="account_disabled")
                raise PortalAccountDisabled()
        return PatientPrincipal(account=account, session_id=claims.session_id)


class SetPortalLanguage:
    """`PATCH /portal/me` (M6b-P2 R21; M6b-P3 R34): the portal language and the slot times.

    Display preferences of the account itself, holding no clinic data: logged, not audited. Slot
    times only place the plan on a clock; they never change a prescription (R28).
    """

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(
        self,
        principal: PatientPrincipal,
        language: Language | None = None,
        slot_times: SlotTimes | None = None,
    ) -> PatientAccountView:
        with self._uow as uow:
            account = uow.patient_accounts.get(principal.account_id, for_update=True)
            if account is None:  # authenticated a moment ago; accounts are never deleted
                raise PortalAccountDisabled()
            now = self._clock.now()
            language_changed = language is not None and account.set_language(language, now=now)
            times_changed = slot_times is not None and account.set_slot_times(slot_times, now=now)
            if language_changed or times_changed:
                uow.patient_accounts.update(account)
                uow.commit()
            if language_changed:
                logger.info(
                    "portal.language_changed",
                    account_id=str(account.id),
                    language=account.language.value,
                )
            if times_changed:
                logger.info("portal.slot_times_changed", account_id=str(account.id))
        return PatientAccountView.of(account)


def account_view(principal: PatientPrincipal) -> PatientAccountView:
    """``GET /portal/me``: authentication already re-read the account."""
    return PatientAccountView.of(principal.account)


def _parse_email(raw: str) -> EmailAddress | None:
    try:
        return EmailAddress.parse(raw)
    except InvalidValue:
        return None
