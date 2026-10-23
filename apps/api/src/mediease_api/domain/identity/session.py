"""Refresh tokens and their families (FR-AUTH-02, spec R5).

A sign-in starts a **family**. Each refresh replaces the presented token with
a successor in the same family. The domain stores only a hash of the token
value; the value itself exists in the user's cookie and nowhere else.

States, derived rather than stored, so they can never disagree::

    ACTIVE   usable: not replaced, not revoked, not expired
    ROTATED  already replaced by a successor — presenting it again is reuse
    REVOKED  ended by sign-out or by a family-wide revocation
    EXPIRED  past expires_at

The same rules serve patient portal sessions (M6a-P3, ADR-0015): there ``user_id`` holds the
owning patient account's ID, and the tokens live in their own table (``patient_refresh_tokens``),
so a staff family and a patient family can never be confused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.errors import InvalidTransition
from mediease_api.domain.shared.time import require_utc


class RefreshTokenState(StrEnum):
    ACTIVE = "ACTIVE"
    ROTATED = "ROTATED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


@dataclass(slots=True)
class RefreshToken:
    """Build new tokens with ``RefreshToken.issue``; the constructor rehydrates."""

    id: UUID
    user_id: UUID
    family_id: UUID
    token_hash: str = field(repr=False)
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None
    replaced_by_id: UUID | None = None

    @classmethod
    def issue(
        cls,
        *,
        id: UUID,
        user_id: UUID,
        family_id: UUID,
        token_hash: str,
        now: datetime,
        ttl: timedelta,
    ) -> RefreshToken:
        now = require_utc(now, "now")
        return cls(
            id=id,
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=now + ttl,
            created_at=now,
            updated_at=now,
        )

    def state(self, now: datetime) -> RefreshTokenState:
        # Order matters: a rotated token is also revoked, and reuse must be recognised.
        if self.replaced_by_id is not None:
            return RefreshTokenState.ROTATED
        if self.revoked_at is not None:
            return RefreshTokenState.REVOKED
        if require_utc(now, "now") >= self.expires_at:
            return RefreshTokenState.EXPIRED
        return RefreshTokenState.ACTIVE

    def mark_replaced(self, successor_id: UUID, *, now: datetime) -> None:
        """Retire this token in favour of ``successor_id`` (one rotation)."""
        state = self.state(now)
        if state is not RefreshTokenState.ACTIVE:
            raise InvalidTransition("refresh token", state, "rotate")
        self.updated_at = self.revoked_at = require_utc(now, "now")
        self.replaced_by_id = successor_id
