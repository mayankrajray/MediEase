"""What a message costs (M5-P5; spec R18; decisions 5A, 6A).

Money is an integer in **millipaise** (1 paisa = 1,000): Meta's Indian rates have four rupee
decimals (utility ₹0.1150 = 11.5 paise), which whole paise per message would round 4% high. Totals
are rounded to paise only when reported.

A price is per unit (a WhatsApp message, an SMS segment) by channel and category, from the date it
takes effect; the table excludes GST. When a message is priced:

- a message of the console provider costs nothing;
- a ``FAILED`` message costs nothing (Meta and SMS providers charge for delivery), except one whose
  outcome is unknown, which a later webhook may still prove delivered;
- WhatsApp: when a status first proves delivery (``DELIVERED`` or ``READ``), at the price for the
  webhook's pricing category on the day of delivery, or nothing if Meta said it is not billable;
- SMS: at acceptance, per segment, category ``transactional``.

An unknown category (or no price yet, such as SMS before L-03) leaves the cost unknown: the ops
total counts it as unpriced rather than guessing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from mediease_api.domain.messaging.errors import MSG_OUTCOME_UNKNOWN
from mediease_api.domain.messaging.message import Channel, Message, MessageStatus
from mediease_api.domain.shared.errors import InvalidValue

CONSOLE_PROVIDER = "console"
SMS_CATEGORY = "transactional"
_DELIVERED = (MessageStatus.DELIVERED, MessageStatus.READ)


@dataclass(frozen=True, slots=True)
class Price:
    channel: Channel
    category: str
    effective_from: date
    millipaise: int

    def __post_init__(self) -> None:
        if self.millipaise < 0:
            raise InvalidValue("millipaise", "must not be negative")
        if not self.category.strip():
            raise InvalidValue("category", "must not be empty")


class PriceTable:
    def __init__(self, prices: Iterable[Price] = ()) -> None:
        self._prices = sorted(prices, key=lambda p: p.effective_from, reverse=True)
        seen = {(p.channel, p.category, p.effective_from) for p in self._prices}
        if len(seen) != len(self._prices):
            raise InvalidValue("prices", "names one channel, category and date twice")

    def per_unit(self, channel: Channel, category: str, on: date) -> int | None:
        for price in self._prices:
            if (
                price.channel is channel
                and price.category == category
                and price.effective_from <= on
            ):
                return price.millipaise
        return None

    def cost(self, message: Message, *, billable: bool | None = None, units: int = 1) -> int | None:
        """The message's cost now, or None while it is not yet known (see the module rules)."""
        if message.status is MessageStatus.QUEUED:
            return None
        if message.status is MessageStatus.FAILED:
            # An unknown outcome may yet prove delivered by a webhook (P2 decision 4A).
            return None if message.error_code == MSG_OUTCOME_UNKNOWN else 0
        if message.provider == CONSOLE_PROVIDER:
            return 0
        if message.channel is Channel.WHATSAPP:
            if message.status not in _DELIVERED or message.delivered_at is None:
                return None
            if billable is False:
                return 0
            if message.pricing_category is None:
                return None
            on = message.delivered_at.date()
            return self.per_unit(Channel.WHATSAPP, message.pricing_category, on)
        if message.channel is Channel.SMS and message.sent_at is not None:
            unit = self.per_unit(Channel.SMS, SMS_CATEGORY, message.sent_at.date())
            return None if unit is None else unit * max(units, 1)
        return None
