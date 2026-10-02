"""AuthenticateRequest — prove the caller on every request (FR-AUTH-03; spec R6, R7, R10).

The access token is verified without the database, but R7 ("no cached
permissions beyond the request") means the facts behind it are re-read every
time, in this order:

1. The token: signature, audience and expiry with 30 s leeway (the adapter).
   Anything wrong → ``AUTH_SESSION_EXPIRED``.
2. The session: its refresh-token family must still have a live token.
   Signing out or a detected token reuse therefore ends access at once,
   instead of when the 15-minute access token runs out.
3. The user: present and ``ACTIVE``.
4. The memberships: an active one somewhere, or platform ops (R10). A
   front-desk member deactivated a moment ago is refused here (AC4).

``resolve_clinic`` then picks the one clinic the request is for (R6). Both
raise; neither returns a partial answer, so a route cannot run half-authorised.

The unit of work is read-only here and rolls back when it closes.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from mediease_api.application.auth._session import may_hold_session
from mediease_api.application.auth.errors import (
    AccountDisabled,
    ClinicRequired,
    ClinicSuspended,
    PermissionDenied,
    SessionExpired,
)
from mediease_api.application.context import Principal
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.identity.access import ClinicAccess
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.security import AccessTokenIssuer, InvalidAccessToken
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class AuthenticateRequest:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, access_tokens: AccessTokenIssuer
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._access_tokens = access_tokens

    def execute(self, access_token: str | None) -> Principal:
        if not access_token:
            raise SessionExpired()
        now = self._clock.now()
        try:
            claims = self._access_tokens.verify(access_token, now=now)
        except InvalidAccessToken:
            # Same answer as a missing token: one error type for "the session is over".
            logger.info("auth.rejected", reason="invalid_token")
            raise SessionExpired() from None

        with self._uow as uow:
            if not uow.refresh_tokens.is_family_live(claims.session_id, now=now):
                logger.info(
                    "auth.rejected",
                    reason="session_ended",
                    user_id=str(claims.user_id),
                    session_id=str(claims.session_id),
                )
                raise SessionExpired()

            user = uow.users.get(claims.user_id)
            access = list(uow.clinic_access.list_active_for_user(claims.user_id)) if user else []
            if user is None or not may_hold_session(user, access):
                reason = "unknown_user" if user is None else "account_disabled"
                logger.info("auth.rejected", reason=reason, user_id=str(claims.user_id))
                raise AccountDisabled()

        return Principal(user=user, session_id=claims.session_id, access=tuple(access))


def resolve_clinic(principal: Principal, requested_clinic_id: str | None) -> ClinicAccess:
    """The one clinic this request is for (R6), or an error that does not leak.

    ``requested_clinic_id`` is the raw ``X-Clinic-ID`` header. A missing header
    is enough for a user with a single membership; anything ambiguous, unknown
    or malformed is ``PERM_CLINIC_REQUIRED``, so the answer never depends on
    whether that clinic exists.
    """
    if principal.is_platform_ops:
        # R10: ops accounts have no clinic business, even if they hold a membership.
        logger.info("perm.denied", reason="platform_ops_on_clinic_route")
        raise PermissionDenied()

    access = _match(principal, requested_clinic_id)
    if access is None:
        logger.info(
            "perm.denied",
            reason="clinic_required",
            user_id=str(principal.user_id),
            clinic_count=len(principal.access),
        )
        raise ClinicRequired()

    if access.clinic_status is ClinicStatus.SUSPENDED:
        logger.info(
            "perm.denied",
            reason="clinic_suspended",
            user_id=str(principal.user_id),
            clinic_id=str(access.clinic_id),
        )
        raise ClinicSuspended()
    return access


def _match(principal: Principal, requested_clinic_id: str | None) -> ClinicAccess | None:
    if requested_clinic_id:
        try:
            wanted = UUID(requested_clinic_id)
        except ValueError:
            return None
        return next((a for a in principal.access if a.clinic_id == wanted), None)
    if len(principal.access) == 1:
        return principal.access[0]
    return None  # none at all, or several and no header: the caller must choose
