"""Security ports: password hashing, access tokens and refresh-token secrets (ADR-0006).

The application decides *when* to hash, sign or verify; these ports decide
*how*. Swapping Argon2 parameters, the JWT library or the token format changes
an adapter only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.shared.errors import DomainError


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str:
        """A self-describing hash (algorithm, parameters and salt included)."""
        ...

    def verify(self, password_hash: str, password: str) -> bool:
        """True only for the right password. A malformed hash is False, never an error."""
        ...

    def needs_rehash(self, password_hash: str) -> bool:
        """True when the hash was made with weaker parameters than the current ones."""
        ...


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    value: str
    expires_at: datetime

    def __repr__(self) -> str:
        return f"IssuedAccessToken(value=<redacted>, expires_at={self.expires_at.isoformat()})"


@dataclass(frozen=True, slots=True)
class AccessClaims:
    """What a verified access token proves: who, and which session (refresh family)."""

    user_id: UUID
    session_id: UUID
    expires_at: datetime


class InvalidAccessToken(DomainError):
    """Expired, tampered with, signed with another key, or not an access token."""

    code = "AUTH_SESSION_EXPIRED"

    def __init__(self) -> None:
        super().__init__("Your session has ended. Please sign in again.")


class AccessTokenIssuer(Protocol):
    def issue(self, *, user_id: UUID, session_id: UUID, now: datetime) -> IssuedAccessToken: ...

    def verify(self, token: str, *, now: datetime) -> AccessClaims:
        """The token's claims, or ``InvalidAccessToken``."""
        ...


class RefreshTokenSecrets(Protocol):
    def generate(self) -> str:
        """A new unguessable token value (goes into the cookie, never into storage)."""
        ...

    def digest(self, token: str) -> str:
        """The value stored and looked up instead of the token itself."""
        ...


class IpHasher(Protocol):
    """Reduces a caller's IP address to a stable, salted fingerprint (M1-P4).

    An audit row needs to answer "was this the same device?", not "which
    address was it": a raw IP is personal data we have no reason to keep.
    """

    def hash(self, ip_address: str | None) -> str | None:
        """The fingerprint, or None when the address is unknown."""
        ...
