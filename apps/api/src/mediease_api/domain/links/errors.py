"""Patient link errors (docs/ERRORS.md "Patient links"). Details: counts and seconds only.

A patient who could not have caused it sees ``LINK_INVALID`` (a changed character, an unknown
key, a link of another purpose or another clinic): the page says nothing more, so a guessed or
tampered token learns nothing.
"""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError


class LinkInvalid(DomainError):
    code = "LINK_INVALID"

    def __init__(self) -> None:
        super().__init__("This link isn't valid.")


class LinkExpired(DomainError):
    code = "LINK_EXPIRED"

    def __init__(self) -> None:
        super().__init__("This link has expired. Ask the clinic for a new one.")


class LinkRevoked(DomainError):
    code = "LINK_REVOKED"

    def __init__(self) -> None:
        super().__init__("This link is no longer active. Ask the clinic for a new one.")


class ChallengeFailed(DomainError):
    """R10: wrong last 4 digits; ``details.attempts_left`` before the link locks."""

    code = "LINK_CHALLENGE_FAILED"

    def __init__(self, attempts_left: int) -> None:
        super().__init__("Those digits don't match.", attempts_left=str(attempts_left))
        self.attempts_left = attempts_left


class LinkLocked(DomainError):
    """R10, AC3: five wrong attempts; only the clinic can unlock it."""

    code = "LINK_LOCKED"

    def __init__(self) -> None:
        super().__init__("Too many attempts. Please contact the clinic.")


class ChallengeRequired(DomainError):
    """The prescription is shown only after the last-4 check, for 30 minutes (R10)."""

    code = "LINK_CHALLENGE_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Enter the last 4 digits of your phone number first.")


class LinkRateLimited(DomainError):
    """Too many requests for one link in a minute; ``retry_after_seconds`` says when."""

    code = "LINK_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many requests. Please wait a moment.")
        self.retry_after_seconds = retry_after_seconds


class LinkNotLocked(DomainError):
    """Resetting a link that is not locked (staff, M4-P5 decision 6A)."""

    code = "LINK_NOT_LOCKED"

    def __init__(self) -> None:
        super().__init__("This link is not locked.")
