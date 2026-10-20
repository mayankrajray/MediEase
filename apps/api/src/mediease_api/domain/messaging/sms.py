"""The SMS fallback's rules (M5-P5; FR-REM-06; decision 4A).

A reminder's WhatsApp (or console) message that ends ``FAILED`` with a definite non-delivery falls
back to one SMS, if the patient consented to SMS. An unknown outcome never does (it may have been
delivered: at most once, P2 decision 4A), nor does a send we skipped ourselves.

Segments: an SMS of GSM-7 characters holds 160 (153 per part when split); anything else, such as
Hindi, is sent as UCS-2 and holds 70 (67 per part). The provider bills per segment.
"""

from __future__ import annotations

from mediease_api.domain.messaging.errors import (
    MSG_PROVIDER_RATE_LIMIT,
    MSG_PROVIDER_REJECTED,
    MSG_PROVIDER_UNAVAILABLE,
    MSG_RECIPIENT_INVALID,
)
from mediease_api.domain.messaging.message import Channel, Message, MessageStatus, SourceType

FALLBACK_CODES = frozenset(
    {
        MSG_RECIPIENT_INVALID,
        MSG_PROVIDER_REJECTED,
        # Only after the last attempt: until then the message is not FAILED.
        MSG_PROVIDER_UNAVAILABLE,
        MSG_PROVIDER_RATE_LIMIT,
    }
)

# The GSM 03.38 basic character set (the extension table counts two; it is not needed here).
_GSM7 = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)


def falls_back_to_sms(message: Message) -> bool:
    return (
        message.source_type is SourceType.REMINDER
        and message.channel is not Channel.SMS
        and message.status is MessageStatus.FAILED
        and message.error_code in FALLBACK_CODES
    )


def sms_segments(text: str) -> int:
    if all(ch in _GSM7 for ch in text):
        single, part = 160, 153
    else:
        single, part = 70, 67
    length = len(text)
    return 1 if length <= single else -(-length // part)
