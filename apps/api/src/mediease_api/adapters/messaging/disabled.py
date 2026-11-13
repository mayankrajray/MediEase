"""Messaging switched off (M9-P1 decision 1; ``MESSAGING_PROVIDER=disabled``).

For a deployment that must not send WhatsApp yet (Meta's setting blocks it): nothing leaves the
machine and nothing pretends to. Every send raises ``ChannelDisabled``, so the message row is
closed with ``MSG_CHANNEL_DISABLED`` and staff see that it was not sent (``MessageSender``).
Unlike the console adapter it is allowed in production, because it never reports a send that did
not happen. Reminders still reach app users in the app and by push (M7e-E4).
"""

from __future__ import annotations

from mediease_api.domain.messaging.errors import ChannelDisabled
from mediease_api.domain.messaging.message import Channel
from mediease_api.ports.messaging import OutboundTemplateMessage, ProviderAccepted

DISABLED_PROVIDER = "disabled"


class DisabledMessagingAdapter:
    @property
    def channel(self) -> Channel:
        # The channel the message would have used, so the row reads "WhatsApp, not sent".
        return Channel.WHATSAPP

    @property
    def provider(self) -> str:
        return DISABLED_PROVIDER

    def send_template(self, msg: OutboundTemplateMessage) -> ProviderAccepted:
        raise ChannelDisabled
