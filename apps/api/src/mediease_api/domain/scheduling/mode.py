"""Booking mode (FR-APT-02): numbered tokens per session, or fixed time slots."""

from __future__ import annotations

from enum import StrEnum


class BookingMode(StrEnum):
    SLOTS = "SLOTS"
    TOKENS = "TOKENS"
