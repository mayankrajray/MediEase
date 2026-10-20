"""Opting out by replying STOP (M5-P5; FR-MSG-05; spec R14, AC5; decisions 1A, 2A).

A patient's WhatsApp reply whose whole text is one of the keywords (trimmed, case-insensitive,
Unicode NFC) opts out every patient with that number in each clinic that has messaged it. Only such
a reply keeps the sender's number in the stored webhook, encrypted, until it is processed; any other
inbound text keeps nothing but its ID, type and time (decision 1A).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime


def _normal(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().casefold()


STOP_KEYWORDS = frozenset(_normal(k) for k in ("stop", "unsubscribe", "रोकें", "बंद"))


def is_stop_keyword(text: str) -> bool:
    return _normal(text) in STOP_KEYWORDS


@dataclass(frozen=True, slots=True, repr=False)
class InboundOptOut:
    """One STOP reply as stored: the provider's message ID, when, and how to find the sender.

    ``phone_encrypted`` is the sender's number under the messages' phone keys; ``context_id`` is
    the provider ID of our message it replied to, the way back to the number when the sender's
    number is hidden (WhatsApp usernames).
    """

    provider_message_id: str
    at: datetime
    phone_encrypted: str | None
    context_id: str | None

    def __repr__(self) -> str:
        return f"InboundOptOut(id={self.provider_message_id}, has_phone={self.has_phone})"

    @property
    def has_phone(self) -> bool:
        return self.phone_encrypted is not None
