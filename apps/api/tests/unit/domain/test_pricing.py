"""What a message costs (M5-P5; spec R18; decisions 5A, 6A)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest

from mediease_api.adapters.messaging.prices import PriceFileInvalid, load_price_table, parse_prices
from mediease_api.application.ops.queries import paise
from mediease_api.domain.messaging.errors import MSG_OUTCOME_UNKNOWN, MSG_RECIPIENT_INVALID
from mediease_api.domain.messaging.message import Channel, Message, MessageStatus, SourceType
from mediease_api.domain.messaging.pricing import Price, PriceTable
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, new_id

OCT = datetime(2026, 10, 20, 4, 0, tzinfo=UTC)
TABLE = PriceTable(
    [
        Price(Channel.WHATSAPP, "utility", date(2026, 1, 1), 11500),
        Price(Channel.WHATSAPP, "service", date(2026, 1, 1), 0),
        Price(Channel.WHATSAPP, "service", date(2026, 10, 1), 11500),
        Price(Channel.SMS, "transactional", date(2026, 1, 1), 20000),
    ]
)


def _message(channel: Channel = Channel.WHATSAPP, **changes: Any) -> Message:
    message = Message.prepare(
        id=new_id(),
        clinic_id=new_id(),
        patient_id=new_id(),
        source_type=SourceType.REMINDER,
        source_id=new_id(),
        channel=channel,
        provider="whatsapp_cloud" if channel is Channel.WHATSAPP else "sms_provider",
        template_key="follow_up_due",
        template_version=1,
        language=Language.EN,
        variables={},
        to_phone_encrypted="x",
        idempotency_key=f"k-{new_id()}",
        request_id=None,
        job_id=None,
        now=NOW,
    )
    message.accepted(provider_message_id=f"p-{new_id()}", now=OCT)
    return replace(message, **changes)


def test_r18_a_price_applies_from_its_date() -> None:
    assert TABLE.per_unit(Channel.WHATSAPP, "service", date(2026, 9, 30)) == 0
    assert TABLE.per_unit(Channel.WHATSAPP, "service", date(2026, 10, 1)) == 11500
    assert TABLE.per_unit(Channel.WHATSAPP, "utility", date(2025, 12, 31)) is None
    assert TABLE.per_unit(Channel.WHATSAPP, "marketing", date(2026, 10, 1)) is None


def test_decision_6a_whatsapp_is_priced_on_delivery_at_its_category() -> None:
    sent = _message(pricing_category="utility")
    assert TABLE.cost(sent) is None  # SENT: not yet
    delivered = replace(sent, status=MessageStatus.DELIVERED, delivered_at=OCT)
    assert TABLE.cost(delivered) == 11500
    assert TABLE.cost(delivered, billable=False) == 0
    assert TABLE.cost(replace(delivered, pricing_category=None)) is None
    assert TABLE.cost(replace(delivered, pricing_category="marketing")) is None  # unpriced


def test_decision_6a_failures_and_the_console_cost_nothing_but_an_unknown_outcome_waits() -> None:
    failed = _message(status=MessageStatus.FAILED, error_code=MSG_RECIPIENT_INVALID)
    assert TABLE.cost(failed) == 0
    unknown = replace(failed, error_code=MSG_OUTCOME_UNKNOWN)
    assert TABLE.cost(unknown) is None
    assert TABLE.cost(_message(Channel.CONSOLE, provider="console")) == 0
    assert TABLE.cost(_message(status=MessageStatus.QUEUED)) is None


def test_r18_an_sms_is_priced_per_segment_at_acceptance() -> None:
    assert TABLE.cost(_message(Channel.SMS), units=2) == 40000
    assert PriceTable().cost(_message(Channel.SMS)) is None  # no SMS price before L-03


def test_decision_5a_the_cost_is_set_once_and_reported_in_paise() -> None:
    message = _message()
    assert not message.settle_cost(None, OCT)
    assert message.settle_cost(11500, OCT) and message.cost_millipaise == 11500
    assert not message.settle_cost(0, OCT) and message.cost_millipaise == 11500
    with pytest.raises(InvalidValue):
        _message().settle_cost(-1, OCT)
    assert (paise(11500), paise(11499), paise(23000), paise(0)) == (12, 11, 23, 0)


def test_the_price_table_refuses_a_duplicate_or_negative_price() -> None:
    with pytest.raises(InvalidValue):
        Price(Channel.WHATSAPP, "utility", date(2026, 1, 1), -1)
    with pytest.raises(InvalidValue):
        PriceTable([TABLE_ENTRY, TABLE_ENTRY])


TABLE_ENTRY = Price(Channel.WHATSAPP, "utility", date(2026, 1, 1), 11500)


def test_the_shipped_price_file_loads_with_the_2026_utility_rate() -> None:
    table = load_price_table()
    assert table.per_unit(Channel.WHATSAPP, "utility", date(2026, 10, 20)) == 11500
    assert table.per_unit(Channel.SMS, "transactional", date(2026, 10, 20)) is None


@pytest.mark.parametrize(
    "text",
    [
        "prices: [",
        "nothing: []",
        "prices: [{channel: WHATSAPP, category: utility, millipaise: 1}]",
        "prices: [{channel: WHATSAPP, category: utility, effective_from: soon, millipaise: 1}]",
        "prices: [{channel: FAX, category: utility, effective_from: 2026-01-01, millipaise: 1}]",
        "prices: [{channel: SMS, category: x, effective_from: 2026-01-01, millipaise: 1.5}]",
        "prices: [7]",
    ],
    ids=["yaml", "no-list", "no-date", "bad-date", "bad-channel", "fraction", "not-mapping"],
)
def test_a_malformed_price_file_stops_start_up(text: str) -> None:
    with pytest.raises(PriceFileInvalid):
        parse_prices(text)
