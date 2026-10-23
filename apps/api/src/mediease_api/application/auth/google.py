"""Google sign-in for staff and patients, run by the API (M6a-P3; FR-AUTH-07; ADR-0015 3, 4, 6).

OpenID Connect Authorization Code flow with PKCE:

1. ``StartGoogleSignIn`` makes a ``state``, a ``nonce`` and a PKCE verifier, seals them with the
   intent (staff or patient) and where to go next into a 10-minute signed cookie, and returns the
   provider's authorization URL. The ``state`` starts with the intent, so even a failed callback
   knows which sign-in page to return to.
2. ``CompleteGoogleSignIn`` opens the cookie, compares ``state``, exchanges the code (the adapter
   verifies the ID token, the nonce included) and decides who this is:

   - **Staff** (decision 4): an identity already linked by Google's ``sub`` signs in that user.
     Otherwise the first sign-in links the active staff user whose email equals Google's
     *verified* email. It never creates staff access, and platform ops users may not use Google.
   - **Patients**: an identity linked by ``sub`` signs in that account; otherwise a new
     ``GOOGLE`` account is created with Google's name and email. A password account with the
     same email is left alone (never merged, decision 5).

Every failure becomes a ``GoogleSignInFailed`` carrying the intent and a reason enum; delivery
turns it into a redirect back to the right sign-in page with a fixed message.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.auth._session import SessionIssuer, may_hold_session, session_result
from mediease_api.application.auth.errors import AuthRateLimited
from mediease_api.application.auth.rate_limit import GOOGLE_PER_MINUTE, enforce_rate_limit
from mediease_api.application.auth.views import SessionResult
from mediease_api.application.context import Actor, RequestInfo
from mediease_api.application.portal.sessions import PatientSessionIssuer, record_patient_event
from mediease_api.application.portal.views import PatientSessionResult
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.external import ExternalIdentity, IdentityProvider
from mediease_api.domain.portal.account import MAX_NAME_LENGTH, PatientAccount, SignInMethod
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.oidc import OidcFailed, OidcIdentity, OidcPort
from mediease_api.ports.security import FlowSealer, InvalidFlow
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

FLOW_TTL = timedelta(minutes=10)
PROVIDER = IdentityProvider.GOOGLE
_MAX_HINT_LENGTH = 254


class GoogleIntent(StrEnum):
    STAFF = "staff"
    PATIENT = "patient"


class FailureReason(StrEnum):
    """Why a Google sign-in did not finish; delivery maps each to a fixed sign-in message."""

    FAILED = "google_failed"
    CANCELLED = "google_cancelled"
    NO_STAFF_ACCOUNT = "google_no_account"
    ACCOUNT_DISABLED = "account_disabled"
    RATE_LIMITED = "too_many_attempts"


class GoogleSignInFailed(DomainError):
    code = "AUTH_GOOGLE_FAILED"

    def __init__(self, intent: GoogleIntent, reason: FailureReason) -> None:
        super().__init__("Google sign-in did not work.", reason=reason.value)
        self.intent = intent
        self.reason = reason


class GoogleNoStaffAccount(GoogleSignInFailed):
    """Google verified an address no active staff user has. Google never creates staff access."""

    code = "AUTH_GOOGLE_NO_STAFF_ACCOUNT"

    def __init__(self) -> None:
        super().__init__(GoogleIntent.STAFF, FailureReason.NO_STAFF_ACCOUNT)


@dataclass(frozen=True, slots=True)
class GoogleStart:
    """Where to send the browser, and the sealed flow for the cookie."""

    authorization_url: str
    flow: str

    def __repr__(self) -> str:
        return "GoogleStart(<redacted>)"


@dataclass(frozen=True, slots=True)
class StaffSignedIn:
    session: SessionResult
    next_path: str


@dataclass(frozen=True, slots=True)
class PatientSignedIn:
    session: PatientSessionResult
    next_path: str


def intent_from_state(state: str | None) -> GoogleIntent | None:
    """The intent a ``state`` was made for: only to pick the page to return to on failure."""
    prefix, _, _ = (state or "").partition(".")
    try:
        return GoogleIntent(prefix)
    except ValueError:
        return None


class StartGoogleSignIn:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        oidc: OidcPort,
        sealer: FlowSealer,
        redirect_uri: str,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._oidc = oidc
        self._sealer = sealer
        self._redirect_uri = redirect_uri

    def execute(
        self,
        intent: GoogleIntent,
        *,
        next_path: str,
        login_hint: str | None,
        info: RequestInfo,
    ) -> GoogleStart:
        _limit(self._uow, self._clock, info, intent)
        state = f"{intent.value}.{secrets.token_urlsafe(32)}"
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)  # 64 characters, inside RFC 7636's 43-128
        sealed = self._sealer.seal(
            {
                "state": state,
                "nonce": nonce,
                "verifier": verifier,
                "intent": intent.value,
                "next": next_path,
            },
            now=self._clock.now(),
            ttl=FLOW_TTL,
        )
        url = self._oidc.authorization_url(
            state=state,
            nonce=nonce,
            code_challenge=pkce_challenge(verifier),
            redirect_uri=self._redirect_uri,
            login_hint=_hint(login_hint),
        )
        logger.info("google.started", intent=intent.value)
        return GoogleStart(authorization_url=url, flow=sealed)


class CompleteGoogleSignIn:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        oidc: OidcPort,
        sealer: FlowSealer,
        redirect_uri: str,
        staff_sessions: SessionIssuer,
        patient_sessions: PatientSessionIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._oidc = oidc
        self._sealer = sealer
        self._redirect_uri = redirect_uri
        self._staff_sessions = staff_sessions
        self._patient_sessions = patient_sessions

    def execute(
        self,
        *,
        flow: str | None,
        state: str | None,
        code: str | None,
        error: str | None,
        info: RequestInfo,
    ) -> StaffSignedIn | PatientSignedIn:
        fallback = intent_from_state(state) or GoogleIntent.STAFF
        _limit(self._uow, self._clock, info, fallback)
        values = self._open(flow, fallback)
        intent = GoogleIntent(values["intent"])
        if not state or not hmac.compare_digest(state.encode(), values["state"].encode()):
            logger.info("google.failed", intent=intent.value, reason="state_mismatch")
            raise GoogleSignInFailed(intent, FailureReason.FAILED)
        if error:
            # e.g. access_denied when the person closes Google's consent screen.
            logger.info("google.failed", intent=intent.value, reason="provider_error")
            raise GoogleSignInFailed(intent, FailureReason.CANCELLED)
        if not code:
            logger.info("google.failed", intent=intent.value, reason="no_code")
            raise GoogleSignInFailed(intent, FailureReason.FAILED)

        try:
            identity = self._oidc.exchange(
                code=code,
                code_verifier=values["verifier"],
                redirect_uri=self._redirect_uri,
                nonce=values["nonce"],
            )
        except OidcFailed as exc:
            logger.info("google.failed", intent=intent.value, reason=exc.reason)
            raise GoogleSignInFailed(intent, FailureReason.FAILED) from None
        email = _verified_email(identity, intent)

        if intent is GoogleIntent.STAFF:
            return StaffSignedIn(self._staff(identity, email, info), values["next"])
        return PatientSignedIn(self._patient(identity, email, info), values["next"])

    def _open(self, flow: str | None, intent: GoogleIntent) -> dict[str, str]:
        try:
            if not flow:
                raise InvalidFlow()
            values = self._sealer.open(flow, now=self._clock.now())
            if not {"state", "nonce", "verifier", "intent", "next"} <= values.keys():
                raise InvalidFlow()
            GoogleIntent(values["intent"])
        except (InvalidFlow, ValueError):
            logger.info("google.failed", intent=intent.value, reason="flow_invalid")
            raise GoogleSignInFailed(intent, FailureReason.FAILED) from None
        return values

    def _staff(
        self, identity: OidcIdentity, email: EmailAddress, info: RequestInfo
    ) -> SessionResult:
        intent = GoogleIntent.STAFF
        with self._uow as uow:
            now = self._clock.now()
            linked = uow.external_identities.get_for_staff(
                PROVIDER, identity.subject, for_update=True
            )
            if linked is not None:
                assert linked.user_id is not None
                user = uow.users.get(linked.user_id, for_update=True)
            else:
                # First Google sign-in: link by Google's verified email, never create (FR-AUTH-07).
                user = uow.users.get_by_email(email, for_update=True)
            if user is None or user.is_platform_ops:
                reason = "unknown_email" if user is None else "platform_ops"
                logger.info("google.failed", intent=intent.value, reason=reason)
                raise GoogleNoStaffAccount()

            access = list(uow.clinic_access.list_active_for_user(user.id))
            if not may_hold_session(user, access):
                logger.info(
                    "google.failed",
                    intent=intent.value,
                    reason="account_disabled",
                    user_id=str(user.id),
                )
                raise GoogleSignInFailed(intent, FailureReason.ACCOUNT_DISABLED)

            if linked is None:
                linked = ExternalIdentity.for_staff(
                    id=self._ids.new_id(),
                    provider=PROVIDER,
                    subject=identity.subject,
                    user_id=user.id,
                    now=now,
                )
                uow.external_identities.add(linked)
                newly_linked = True
            else:
                linked.record_use(now=now)
                uow.external_identities.update(linked)
                newly_linked = False

            user.record_successful_sign_in(now=now)
            uow.users.update(user)
            family_id = self._ids.new_id()
            _, tokens = self._staff_sessions.issue(
                uow, user_id=user.id, family_id=family_id, now=now
            )
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.STAFF_SIGNED_IN_GOOGLE,
                actor=Actor.for_user(user, info),
                now=now,
                metadata={
                    "session_id": str(family_id),
                    "clinic_count": str(len(access)),
                    "linked": str(newly_linked).lower(),
                },
            )
            uow.commit()
        logger.info(
            "google.staff_signed_in",
            user_id=str(user.id),
            session_id=str(family_id),
            linked=newly_linked,
        )
        return session_result(user, access, tokens)

    def _patient(
        self, identity: OidcIdentity, email: EmailAddress, info: RequestInfo
    ) -> PatientSessionResult:
        intent = GoogleIntent.PATIENT
        with self._uow as uow:
            now = self._clock.now()
            linked = uow.external_identities.get_for_patient(
                PROVIDER, identity.subject, for_update=True
            )
            created = linked is None
            if linked is not None:
                assert linked.patient_account_id is not None
                account = uow.patient_accounts.get(linked.patient_account_id, for_update=True)
                if account is None or not account.is_active:
                    logger.info("google.failed", intent=intent.value, reason="account_disabled")
                    raise GoogleSignInFailed(intent, FailureReason.ACCOUNT_DISABLED)
                linked.record_use(now=now)
                uow.external_identities.update(linked)
            else:
                account = PatientAccount.from_google(
                    id=self._ids.new_id(),
                    full_name=_display_name(identity, email),
                    email=email,
                    now=now,
                )
                uow.patient_accounts.add(account)
                uow.external_identities.add(
                    ExternalIdentity.for_patient(
                        id=self._ids.new_id(),
                        provider=PROVIDER,
                        subject=identity.subject,
                        patient_account_id=account.id,
                        now=now,
                    )
                )
            account.record_successful_sign_in(now=now)
            uow.patient_accounts.update(account)
            session_id, result = self._patient_sessions.start(uow, account, now=now)
            method = SignInMethod.GOOGLE.value
            if created:
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
        logger.info(
            "google.patient_signed_in",
            account_id=str(account.id),
            session_id=str(session_id),
            created=created,
        )
        return result


def pkce_challenge(verifier: str) -> str:
    """RFC 7636 S256: base64url(sha256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _limit(uow: UnitOfWork, clock: ClockPort, info: RequestInfo, intent: GoogleIntent) -> None:
    try:
        enforce_rate_limit(uow, clock, info, bucket="google", limit=GOOGLE_PER_MINUTE)
    except AuthRateLimited:
        raise GoogleSignInFailed(intent, FailureReason.RATE_LIMITED) from None


def _hint(raw: str | None) -> str | None:
    """A login hint only if it looks like an email; anything else is dropped, not refused."""
    if not raw or len(raw) > _MAX_HINT_LENGTH:
        return None
    try:
        return EmailAddress.parse(raw).value
    except InvalidValue:
        return None


def _verified_email(identity: OidcIdentity, intent: GoogleIntent) -> EmailAddress:
    if not identity.email_verified:
        logger.info("google.failed", intent=intent.value, reason="email_not_verified")
        raise GoogleSignInFailed(intent, FailureReason.FAILED)
    try:
        return EmailAddress.parse(identity.email)
    except InvalidValue:
        logger.info("google.failed", intent=intent.value, reason="email_invalid")
        raise GoogleSignInFailed(intent, FailureReason.FAILED) from None


def _display_name(identity: OidcIdentity, email: EmailAddress) -> str:
    """Google's name, or the address's local part when Google sent none."""
    name = " ".join((identity.name or "").split())
    if not name:
        name = email.value.rpartition("@")[0]
    return name[:MAX_NAME_LENGTH]
