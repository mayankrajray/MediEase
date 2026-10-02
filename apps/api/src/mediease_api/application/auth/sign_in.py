"""SignIn — email or phone + password (FR-AUTH-01, FR-AUTH-04; spec R1-R4).

Order of checks, and why:

1. Normalise the identifier (R1). Anything that is neither an email nor a
   phone number is treated like an unknown account.
2. Load the user **with a row lock**, so concurrent wrong passwords are
   counted one after another.
3. Unknown user, or no password set → verify against a dummy hash anyway, so
   the response takes as long as for a real account (R2).
4. Locked → ``AUTH_LOCKED`` without checking the password (R3, AC1). The
   dummy verification keeps the timing uniform here too.
5. Wrong password → count it (the fifth locks the account), commit, and
   answer ``AUTH_INVALID_CREDENTIALS``.
6. Right password but disabled, or no active membership and not ops →
   ``AUTH_ACCOUNT_DISABLED``; the failure count is untouched.
7. Success → reset the count, upgrade the hash if parameters rose, start a
   new token family, commit.

Audited (M1-P4): the successful sign-in, and the failures that are bounded —
a wrong password (the lockout caps them) and an account that cannot hold a
session despite the correct password. Unknown identifiers, users with no
password and attempts while locked are logged only, because nothing
rate-limits them and an audit row per attempt would be a flood.

Logs carry the user ID and an enum ``reason`` — never the identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import structlog

from mediease_api.application.audit import record_user_event
from mediease_api.application.auth._session import SessionIssuer, may_hold_session, session_result
from mediease_api.application.auth.errors import AccountDisabled, AccountLocked, InvalidCredentials
from mediease_api.application.auth.views import SessionResult
from mediease_api.application.context import RequestInfo
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.user import User
from mediease_api.domain.shared.email import EmailAddress
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import PasswordHasher
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SignInCommand:
    identifier: str
    password: str

    def __repr__(self) -> str:
        return "SignInCommand(<redacted>)"


class SignIn:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        hasher: PasswordHasher,
        sessions: SessionIssuer,
        dummy_password_hash: str,
    ) -> None:
        # dummy_password_hash: a real hash of a random password, made once at
        # start-up, so unknown accounts cost one Argon2 verification too.
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._hasher = hasher
        self._sessions = sessions
        self._dummy_hash = dummy_password_hash

    def execute(self, cmd: SignInCommand, info: RequestInfo | None = None) -> SessionResult:
        info = info or RequestInfo()
        identifier = _parse_identifier(cmd.identifier)
        with self._uow as uow:
            now = self._clock.now()
            user = _find_user(uow, identifier)

            if user is None or user.password_hash is None:
                self._hasher.verify(self._dummy_hash, cmd.password)
                reason = "unknown_identifier" if user is None else "no_password"
                # Not audited: neither path is rate-limited, so recording them
                # would let anyone grow the audit table (M1-P4 design).
                logger.info("auth.sign_in_failed", reason=reason)
                raise InvalidCredentials()

            if user.is_locked(now):
                self._hasher.verify(self._dummy_hash, cmd.password)
                assert user.locked_until is not None
                retry_after = max(1, int((user.locked_until - now).total_seconds()))
                # Not audited either: the five failures that caused the lock are.
                logger.info("auth.sign_in_failed", reason="locked", user_id=str(user.id))
                raise AccountLocked(retry_after)

            if not self._hasher.verify(user.password_hash, cmd.password):
                locked_now = user.record_failed_sign_in(now=now)
                uow.users.update(user)
                self._audit(
                    uow,
                    user,
                    info,
                    now,
                    AuditAction.AUTH_SIGN_IN_FAILED,
                    {"reason": "wrong_password", "locked": str(locked_now).lower()},
                )
                uow.commit()
                logger.info("auth.sign_in_failed", reason="wrong_password", user_id=str(user.id))
                if locked_now:
                    logger.warning("auth.locked", user_id=str(user.id))
                raise InvalidCredentials()

            access = list(uow.clinic_access.list_active_for_user(user.id))
            if not may_hold_session(user, access):
                reason = "disabled" if not user.is_active else "no_active_membership"
                # Audited: reaching this point took the correct password.
                self._audit(
                    uow, user, info, now, AuditAction.AUTH_SIGN_IN_FAILED, {"reason": reason}
                )
                uow.commit()
                logger.info("auth.sign_in_failed", reason=reason, user_id=str(user.id))
                raise AccountDisabled()

            if self._hasher.needs_rehash(user.password_hash):
                user.set_password_hash(self._hasher.hash(cmd.password), now=now)
            user.record_successful_sign_in(now=now)
            uow.users.update(user)
            family_id = self._ids.new_id()
            _, tokens = self._sessions.issue(uow, user_id=user.id, family_id=family_id, now=now)
            self._audit(
                uow,
                user,
                info,
                now,
                AuditAction.AUTH_SIGNED_IN,
                {"session_id": str(family_id), "clinic_count": str(len(access))},
            )
            uow.commit()

        logger.info("auth.signed_in", user_id=str(user.id), session_id=str(family_id))
        return session_result(user, access, tokens)

    def _audit(
        self,
        uow: UnitOfWork,
        user: User,
        info: RequestInfo,
        now: datetime,
        action: AuditAction,
        metadata: dict[str, str],
    ) -> None:
        record_user_event(
            uow,
            event_id=self._ids.new_id(),
            action=action,
            user=user,
            info=info,
            now=now,
            metadata=metadata,
        )


def _parse_identifier(raw: str) -> EmailAddress | PhoneNumber | None:
    try:
        if "@" in raw:
            return EmailAddress.parse(raw, field="identifier")
        return PhoneNumber.parse(raw, field="identifier")
    except InvalidValue:
        return None


def _find_user(uow: UnitOfWork, identifier: EmailAddress | PhoneNumber | None) -> User | None:
    if isinstance(identifier, EmailAddress):
        return uow.users.get_by_email(identifier, for_update=True)
    if isinstance(identifier, PhoneNumber):
        return uow.users.get_by_phone(identifier, for_update=True)
    return None
