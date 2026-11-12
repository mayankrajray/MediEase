"""A push adapter that only logs (M7e-E3): local, CI and tests; refused in production.

It logs that a push would leave, never the endpoint or the message. ``sent`` keeps what was handed
over in memory so a test can read it.
"""

from __future__ import annotations

import structlog

from mediease_api.ports.push import PushTarget

logger = structlog.get_logger(__name__)


class ConsolePushAdapter:
    provider = "console"

    def __init__(self) -> None:
        self.sent: list[tuple[PushTarget, str, int]] = []

    def send(self, target: PushTarget, data: str, *, ttl: int) -> None:
        self.sent.append((target, data, ttl))
        logger.info("push.console_sent", provider=self.provider, ttl=ttl, size=len(data))
