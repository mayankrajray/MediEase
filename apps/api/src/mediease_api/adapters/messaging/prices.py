"""The price table, read from ``prices.yaml`` once at start-up (M5-P5; spec R18; decision 6A).

A malformed file stops the worker before it claims anything, like the templates file.
``yaml.safe_load`` only: the file is data, never objects.
"""

from __future__ import annotations

from datetime import date
from importlib import resources
from typing import Any

import yaml

from mediease_api.domain.messaging.message import Channel
from mediease_api.domain.messaging.pricing import Price, PriceTable
from mediease_api.domain.shared.errors import InvalidValue


class PriceFileInvalid(ValueError):
    """The prices file cannot be used; the message says where."""


def _price(n: int, raw: Any) -> Price:
    where = f"prices[{n}]"
    if not isinstance(raw, dict):
        raise PriceFileInvalid(f"{where}: must be a mapping")
    try:
        effective = raw["effective_from"]
        if not isinstance(effective, date):
            raise PriceFileInvalid(f"{where}: effective_from must be a date (YYYY-MM-DD)")
        millipaise = raw["millipaise"]
        if not isinstance(millipaise, int) or isinstance(millipaise, bool):
            raise PriceFileInvalid(f"{where}: millipaise must be a whole number")
        return Price(
            channel=Channel(raw["channel"]),
            category=str(raw["category"]),
            effective_from=effective,
            millipaise=millipaise,
        )
    except KeyError as missing:
        raise PriceFileInvalid(f"{where}: {missing} is missing") from None
    except (InvalidValue, ValueError) as error:
        if isinstance(error, PriceFileInvalid):
            raise
        raise PriceFileInvalid(f"{where}: {error}") from None


def parse_prices(text: str) -> PriceTable:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        raise PriceFileInvalid("prices file is not valid YAML") from None
    raw = document.get("prices") if isinstance(document, dict) else None
    if not isinstance(raw, list):
        raise PriceFileInvalid("file: 'prices' must be a list")
    try:
        return PriceTable(_price(n, entry) for n, entry in enumerate(raw))
    except InvalidValue as error:
        raise PriceFileInvalid(f"file: {error}") from None


def load_price_table() -> PriceTable:
    text = (
        resources.files("mediease_api.adapters.messaging")
        .joinpath("prices.yaml")
        .read_text(encoding="utf-8")
    )
    return parse_prices(text)
