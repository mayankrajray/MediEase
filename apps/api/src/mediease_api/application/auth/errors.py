"""Authentication errors (docs/ERRORS.md "Auth and permissions").

Messages are safe to show to clinic staff and deliberately vague: none says
whether the account exists or which part of the credentials was wrong (R2).
"""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError


class InvalidCredentials(DomainError):
    code = "AUTH_INVALID_CREDENTIALS"

    def __init__(self) -> None:
        super().__init__("The sign-in details are not correct.")


class AccountLocked(DomainError):
    """Too many consecutive failures (FR-AUTH-04, R3)."""

    code = "AUTH_LOCKED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many attempts. Try again in a few minutes.",
            retry_after_seconds=str(retry_after_seconds),
        )
        self.retry_after_seconds = retry_after_seconds


class AccountDisabled(DomainError):
    """Right password, but the user is disabled or has no active clinic membership (R7)."""

    code = "AUTH_ACCOUNT_DISABLED"

    def __init__(self) -> None:
        super().__init__("This account is not active. Contact your clinic owner.")


class SessionExpired(DomainError):
    """The refresh token is unknown, expired or revoked: sign in again."""

    code = "AUTH_SESSION_EXPIRED"

    def __init__(self) -> None:
        super().__init__("Your session has ended. Please sign in again.")


class RefreshTokenReused(DomainError):
    """An already-rotated refresh token was presented; its family is now revoked (R5)."""

    code = "AUTH_REFRESH_REUSED"

    def __init__(self) -> None:
        super().__init__("For your safety this session was ended. Please sign in again.")
