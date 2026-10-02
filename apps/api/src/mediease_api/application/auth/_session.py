"""Shared session steps for sign-in and refresh: who may hold a session, and new tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from mediease_api.application.auth.views import (
    MembershipView,
    SessionResult,
    SessionTokens,
    UserView,
)
from mediease_api.domain.identity.access import ClinicAccess
from mediease_api.domain.identity.session import RefreshToken
from mediease_api.domain.identity.user import User
from mediease_api.ports.ids import IdPort
from mediease_api.ports.security import AccessTokenIssuer, RefreshTokenSecrets
from mediease_api.ports.unit_of_work import UnitOfWork


def may_hold_session(user: User, access: list[ClinicAccess]) -> bool:
    """Active users with a clinic to work in, or platform ops (who have none by default, R10)."""
    return user.is_active and (user.is_platform_ops or bool(access))


@dataclass(frozen=True, slots=True)
class SessionIssuer:
    """Creates a refresh token in a family and the matching access token."""

    ids: IdPort
    secrets: RefreshTokenSecrets
    access_tokens: AccessTokenIssuer
    refresh_ttl: timedelta

    def issue(
        self, uow: UnitOfWork, *, user_id: UUID, family_id: UUID, now: datetime
    ) -> tuple[RefreshToken, SessionTokens]:
        value = self.secrets.generate()
        refresh = RefreshToken.issue(
            id=self.ids.new_id(),
            user_id=user_id,
            family_id=family_id,
            token_hash=self.secrets.digest(value),
            now=now,
            ttl=self.refresh_ttl,
        )
        uow.refresh_tokens.add(refresh)
        access = self.access_tokens.issue(user_id=user_id, session_id=family_id, now=now)
        tokens = SessionTokens(
            access_token=access.value,
            access_expires_at=access.expires_at,
            refresh_token=value,
            refresh_expires_at=refresh.expires_at,
        )
        return refresh, tokens


def session_result(user: User, access: list[ClinicAccess], tokens: SessionTokens) -> SessionResult:
    return SessionResult(
        user=UserView.of(user),
        memberships=tuple(MembershipView.of(a) for a in access),
        tokens=tokens,
    )
