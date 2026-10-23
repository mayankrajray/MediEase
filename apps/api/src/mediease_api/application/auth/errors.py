"""Authentication errors (docs/ERRORS.md "Auth and permissions").

Messages are safe to show to clinic staff and deliberately vague: none says
whether the account exists or which part of the credentials was wrong (R2).
The ``PERM_*`` errors answer "not for you, here" without describing what you
asked for (R6, R8, R10).
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


class PermissionDenied(DomainError):
    """The caller is authenticated but may not do this here (FR-AUTH-03, R10).

    ``details`` names the permission the endpoint needed and the caller's own
    role — facts they already know — never anything about the resource.
    """

    code = "PERM_DENIED"

    def __init__(self, *, permission: str | None = None, role: str | None = None) -> None:
        details = {k: v for k, v in (("permission", permission), ("role", role)) if v}
        super().__init__("You do not have access to this action.", **details)


class ClinicRequired(DomainError):
    """R6: the request did not identify exactly one clinic the user may work in.

    The same answer whether ``X-Clinic-ID`` was missing, malformed, or named a
    clinic this user has no membership in, so it never reveals that a clinic
    exists.
    """

    code = "PERM_CLINIC_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Choose which clinic this request is for.")


class ClinicSuspended(DomainError):
    """The resolved clinic is ``SUSPENDED``: nobody works in it until it is reactivated."""

    code = "CLN_SUSPENDED"

    def __init__(self) -> None:
        super().__init__("This clinic is suspended. Contact MediEase support.")


class AuthRateLimited(DomainError):
    """Too many sign-up, sign-in or Google attempts from one caller (M6a-P3, decision 7)."""

    code = "AUTH_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many attempts. Wait a minute and try again.",
            retry_after_seconds=str(retry_after_seconds),
        )
        self.retry_after_seconds = retry_after_seconds
