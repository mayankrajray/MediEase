"""Assistant errors raised by the use cases (spec assistant R11; docs/ERRORS.md)."""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError


class RateLimited(DomainError):
    """R11: more than 12 turns a minute for one account or staff user."""

    code = "AI_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many messages. Please wait a moment and try again.")
        self.retry_after_seconds = retry_after_seconds
