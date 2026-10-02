"""SignOut — end the session's whole token family (FR-AUTH-02).

Idempotent and silent: an unknown, expired or already-revoked token is not an
error, because the outcome the user wants (signed out) already holds.
Delivery clears the cookies either way. Access tokens already issued for the
family stay valid until they expire (at most 15 minutes); M1-P3 also refuses
them once their family is revoked.
"""

from __future__ import annotations

import structlog

from mediease_api.ports.clock import ClockPort
from mediease_api.ports.security import RefreshTokenSecrets
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class SignOut:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, secrets: RefreshTokenSecrets) -> None:
        self._uow = uow
        self._clock = clock
        self._secrets = secrets

    def execute(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        digest = self._secrets.digest(refresh_token)
        with self._uow as uow:
            token = uow.refresh_tokens.get_by_hash(digest, for_update=True)
            if token is None:
                return
            revoked = uow.refresh_tokens.revoke_family(token.family_id, now=self._clock.now())
            uow.commit()
        logger.info(
            "auth.signed_out",
            user_id=str(token.user_id),
            session_id=str(token.family_id),
            revoked_count=revoked,
        )
