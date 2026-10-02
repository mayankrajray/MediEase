"""RefreshSession — rotate a refresh token, detect reuse (FR-AUTH-02; spec R5, AC2).

The presented token is looked up by digest **under a row lock**:

- unknown, expired or revoked → ``AUTH_SESSION_EXPIRED``;
- already rotated → someone holds a copy: revoke the whole family, commit,
  ``AUTH_REFRESH_REUSED`` (the newer token stops working too);
- active → check the user may still hold a session (R7: disabled users and
  users without an active membership lose the family), then issue a
  successor in the same family and retire the presented token.

Two parallel refreshes with one token are serialised by the lock: the second
sees a rotated token and ends the family. That is the strict reading of R5;
the web client serialises its refreshes (M1-P6).
"""

from __future__ import annotations

import structlog

from mediease_api.application.audit import record_user_event
from mediease_api.application.auth._session import SessionIssuer, may_hold_session, session_result
from mediease_api.application.auth.errors import (
    AccountDisabled,
    RefreshTokenReused,
    SessionExpired,
)
from mediease_api.application.auth.views import SessionResult
from mediease_api.application.context import RequestInfo
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.identity.session import RefreshTokenState
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import RefreshTokenSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class RefreshSession:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        secrets: RefreshTokenSecrets,
        sessions: SessionIssuer,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets
        self._sessions = sessions

    def execute(self, refresh_token: str, info: RequestInfo | None = None) -> SessionResult:
        info = info or RequestInfo()
        digest = self._secrets.digest(refresh_token)
        with self._uow as uow:
            now = self._clock.now()
            token = uow.refresh_tokens.get_by_hash(digest, for_update=True)
            if token is None:
                logger.info("auth.refresh_failed", reason="unknown")
                raise SessionExpired()

            state = token.state(now)
            if state is RefreshTokenState.ROTATED:
                revoked = uow.refresh_tokens.revoke_family(token.family_id, now=now)
                user = uow.users.get(token.user_id)
                if user is not None:
                    # Possible token theft: the audit trail must show it even
                    # though no account state changed (spec R5).
                    record_user_event(
                        uow,
                        event_id=self._ids.new_id(),
                        action=AuditAction.AUTH_REFRESH_REUSED,
                        user=user,
                        info=info,
                        now=now,
                        metadata={
                            "session_id": str(token.family_id),
                            "revoked_count": str(revoked),
                        },
                    )
                uow.commit()
                logger.warning(
                    "auth.refresh_reused",
                    user_id=str(token.user_id),
                    session_id=str(token.family_id),
                    revoked_count=revoked,
                )
                raise RefreshTokenReused()
            if state is not RefreshTokenState.ACTIVE:
                logger.info("auth.refresh_failed", reason=state.value.lower())
                raise SessionExpired()

            user = uow.users.get(token.user_id)
            access = list(uow.clinic_access.list_active_for_user(token.user_id)) if user else []
            if user is None or not may_hold_session(user, access):
                uow.refresh_tokens.revoke_family(token.family_id, now=now)
                uow.commit()
                logger.info("auth.refresh_failed", reason="account_disabled")
                raise AccountDisabled()

            successor, tokens = self._sessions.issue(
                uow, user_id=user.id, family_id=token.family_id, now=now
            )
            token.mark_replaced(successor.id, now=now)
            uow.refresh_tokens.update(token)
            uow.commit()

        logger.info("auth.refreshed", user_id=str(user.id), session_id=str(token.family_id))
        return session_result(user, access, tokens)
