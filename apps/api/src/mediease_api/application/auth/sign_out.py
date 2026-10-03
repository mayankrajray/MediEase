"""SignOut — end the session's whole token family (FR-AUTH-02).

Idempotent and silent: an unknown, expired or already-revoked token is not an
error, because the outcome the user wants (signed out) already holds.
Delivery clears the cookies either way. M1-P3 refuses access tokens whose
family is revoked, so access ends with this call rather than minutes later,
and M1-P4 records ``auth.signed_out`` in the same transaction.
"""

from __future__ import annotations

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestInfo
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import RefreshTokenSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class SignOut:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, secrets: RefreshTokenSecrets
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._secrets = secrets

    def execute(self, refresh_token: str | None, info: RequestInfo | None = None) -> None:
        if not refresh_token:
            return
        info = info or RequestInfo()
        digest = self._secrets.digest(refresh_token)
        with self._uow as uow:
            token = uow.refresh_tokens.get_by_hash(digest, for_update=True)
            if token is None:
                return
            now = self._clock.now()
            revoked = uow.refresh_tokens.revoke_family(token.family_id, now=now)
            user = uow.users.get(token.user_id)
            if user is not None:
                record_event(
                    uow,
                    event_id=self._ids.new_id(),
                    action=AuditAction.AUTH_SIGNED_OUT,
                    actor=Actor.for_user(user, info),
                    now=now,
                    metadata={
                        "session_id": str(token.family_id),
                        "revoked_count": str(revoked),
                    },
                )
            uow.commit()
        logger.info(
            "auth.signed_out",
            user_id=str(token.user_id),
            session_id=str(token.family_id),
            revoked_count=revoked,
        )
