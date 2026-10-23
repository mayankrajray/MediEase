"""An email adapter that only logs (M6a-P4). For unit tests; refused in production.

It logs the masked recipient and the subject, never the body: the body carries a single-use link.
``sent`` keeps the messages in memory so a test can read the link.
"""

from __future__ import annotations

import structlog

from mediease_api.ports.email import EmailMessage

logger = structlog.get_logger(__name__)


class ConsoleEmailAdapter:
    provider = "console"

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
        logger.info(
            "email.console_sent",
            provider=self.provider,
            to=message.to.masked(),
            subject=message.subject,
        )
