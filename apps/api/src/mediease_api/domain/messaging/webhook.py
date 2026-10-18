"""A stored provider webhook (M5-P3; spec R13; decisions 2A, 3A).

Stored once per body (``event_key`` is the SHA-256 of the raw bytes, so Meta's redeliveries are
recognised) and processed later by a job. The payload is the redacted form: statuses and IDs only,
never message text, profile names or phone numbers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from mediease_api.domain.shared.time import require_utc

# What a status that matches no message waits for: the webhook can beat our own commit.
MAX_UNMATCHED_ATTEMPTS = 5


@dataclass(slots=True)
class WebhookEvent:
    id: UUID
    provider: str
    event_key: str
    payload: Mapping[str, Any]
    received_at: datetime
    processed_at: datetime | None = None
    error_code: str | None = None

    @classmethod
    def receive(
        cls,
        *,
        id: UUID,
        provider: str,
        event_key: str,
        payload: Mapping[str, Any],
        now: datetime,
    ) -> WebhookEvent:
        return cls(
            id=id,
            provider=provider,
            event_key=event_key,
            payload=payload,
            received_at=require_utc(now, "now"),
        )
