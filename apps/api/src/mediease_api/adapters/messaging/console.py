"""The console provider: development and tests (ADR-0007; ``MESSAGING_PROVIDER=console``).

Nothing leaves the machine. Each accepted message is one ``messaging.console_accepted`` log line
with the template, language, the masked number and the variable *names* — never the values, which
include the signed link. The ``messages`` row is the record of what was sent.

It answers a repeated ``idempotency_key`` with the first provider ID, as a real provider with
idempotency would; that memory is per process and is not what keeps sends single (the message
row's unique key does that, R6).
"""

from __future__ import annotations

import threading
import uuid

import structlog

from mediease_api.domain.messaging.message import Channel
from mediease_api.ports.messaging import OutboundTemplateMessage, ProviderAccepted

logger = structlog.get_logger(__name__)


class ConsoleMessagingAdapter:
    def __init__(self) -> None:
        self._accepted: dict[str, str] = {}
        self._lock = threading.Lock()
        self.calls = 0

    @property
    def channel(self) -> Channel:
        return Channel.CONSOLE

    @property
    def provider(self) -> str:
        return "console"

    def send_template(self, msg: OutboundTemplateMessage) -> ProviderAccepted:
        with self._lock:
            self.calls += 1
            provider_id = self._accepted.get(msg.idempotency_key)
            repeat = provider_id is not None
            if provider_id is None:
                # Unique across processes and restarts, like a real provider's message ID (the
                # column is unique for the status webhooks of P3).
                provider_id = f"console-{uuid.uuid4().hex}"
                self._accepted[msg.idempotency_key] = provider_id
        logger.info(
            "messaging.console_accepted",
            template=msg.template.key,
            template_version=msg.template.version,
            language=msg.language.value,
            to=msg.to.masked(),
            variables=sorted(msg.variables),
            provider_message_id=provider_id,
            repeat=repeat,
        )
        return ProviderAccepted(provider_message_id=provider_id)
