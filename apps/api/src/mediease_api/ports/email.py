"""Email port (M6a-P4, ADR-0016 decision 1).

The application decides *what* to say and to whom; the adapter decides *how* it leaves: SMTP to
Brevo, Resend, SES or the local Mailpit, or the console in tests. Messages hold no clinical
content and no tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from mediease_api.domain.shared.email import EmailAddress


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: EmailAddress
    subject: str
    text: str
    html: str

    def __repr__(self) -> str:
        # The body carries a single-use link: never print it.
        return f"EmailMessage(to={self.to!r}, subject={self.subject!r}, body=<redacted>)"


class EmailFailed(Exception):
    """The provider did not accept the message. ``retryable`` failures are tried again later."""

    def __init__(self, reason: str, *, retryable: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class EmailPort(Protocol):
    @property
    def provider(self) -> str:
        """For logs: ``smtp`` or ``console``."""
        ...

    def send(self, message: EmailMessage) -> None:
        """Hand the message over, or raise ``EmailFailed``."""
        ...
