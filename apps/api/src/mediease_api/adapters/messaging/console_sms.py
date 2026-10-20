"""The console SMS provider: the SMS fallback in development and tests (M5-P5; FR-REM-06).

The real SMS adapter waits for L-03 (the provider, its DLT template IDs and sender ID), so
``SMS_PROVIDER=console`` is the only choice today and is refused in production while the fallback
is on (bootstrap). Nothing leaves the machine: each accepted SMS is one
``messaging.console_sms_accepted`` log line with the template, language, masked number, length
and segment count — never the text, which carries the clinic's and doctor's names.

A template without SMS wording is refused (``MSG_TEMPLATE_NOT_FOUND``): nothing was sent.
"""

from __future__ import annotations

import threading
import uuid

import structlog

from mediease_api.domain.messaging.errors import MSG_TEMPLATE_NOT_FOUND, ProviderRefused
from mediease_api.domain.messaging.message import Channel
from mediease_api.domain.messaging.sms import sms_segments
from mediease_api.ports.messaging import OutboundTemplateMessage, ProviderAccepted

logger = structlog.get_logger(__name__)


class ConsoleSmsAdapter:
    def __init__(self) -> None:
        self._accepted: dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def channel(self) -> Channel:
        return Channel.SMS

    @property
    def provider(self) -> str:
        return "console"

    def send_template(self, msg: OutboundTemplateMessage) -> ProviderAccepted:
        if not msg.template.has_sms:
            raise ProviderRefused(MSG_TEMPLATE_NOT_FOUND)
        text = msg.template.render_sms(msg.language, msg.variables)
        with self._lock:
            provider_id = self._accepted.get(msg.idempotency_key)
            repeat = provider_id is not None
            if provider_id is None:
                provider_id = f"console-sms-{uuid.uuid4().hex}"
                self._accepted[msg.idempotency_key] = provider_id
        logger.info(
            "messaging.console_sms_accepted",
            template=msg.template.key,
            language=msg.language.value,
            to=msg.to.masked(),
            length=len(text),
            segments=sms_segments(text),
            provider_message_id=provider_id,
            repeat=repeat,
        )
        return ProviderAccepted(provider_message_id=provider_id)
