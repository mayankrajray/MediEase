"""Errors of web push subscriptions (M7e-E2; docs/ERRORS.md "Web push")."""

from __future__ import annotations

from mediease_api.domain.push.subscription import MAX_DEVICES
from mediease_api.domain.shared.errors import DomainError


class TooManyDevices(DomainError):
    """The owner already has the most devices allowed; one must be removed first."""

    code = "PSH_TOO_MANY_DEVICES"

    def __init__(self) -> None:
        super().__init__(f"Notifications are on for {MAX_DEVICES} devices. Turn one off first.")


class PushRateLimited(DomainError):
    """Too many subscribe calls from one owner in an hour."""

    code = "PSH_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many attempts. Please wait a little and try again.")
        self.retry_after_seconds = retry_after_seconds
