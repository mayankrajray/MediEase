"""Meta's WhatsApp Cloud API error codes mapped to ours (M5-P3; spec R7; docs/ERRORS.md).

Used for the send call's error response and for ``failed`` statuses in webhooks, which carry the
same codes. Only throttling and Meta-side outages are retryable; anything else Meta refused is
permanent. An unlisted code is ``MSG_PROVIDER_REJECTED``: Meta said no, and guessing it is
retryable could send a message twice.
"""

from __future__ import annotations

from mediease_api.domain.messaging.errors import (
    MSG_PROVIDER_AUTH,
    MSG_PROVIDER_RATE_LIMIT,
    MSG_PROVIDER_REJECTED,
    MSG_PROVIDER_UNAVAILABLE,
    MSG_RECIPIENT_INVALID,
    MSG_TEMPLATE_NOT_FOUND,
    MSG_TEMPLATE_PARAMS,
)

_CODES: dict[int, str] = {
    # Throughput (messages per second), per-recipient pair limit, account rate limit, API calls.
    130429: MSG_PROVIDER_RATE_LIMIT,
    131056: MSG_PROVIDER_RATE_LIMIT,
    80007: MSG_PROVIDER_RATE_LIMIT,
    4: MSG_PROVIDER_RATE_LIMIT,
    # Meta-side errors and temporary unavailability.
    1: MSG_PROVIDER_UNAVAILABLE,
    2: MSG_PROVIDER_UNAVAILABLE,
    131000: MSG_PROVIDER_UNAVAILABLE,
    131016: MSG_PROVIDER_UNAVAILABLE,
    133004: MSG_PROVIDER_UNAVAILABLE,
    # Template missing, paused or disabled.
    132001: MSG_TEMPLATE_NOT_FOUND,
    132015: MSG_TEMPLATE_NOT_FOUND,
    132016: MSG_TEMPLATE_NOT_FOUND,
    # Parameters do not match the approved template.
    132000: MSG_TEMPLATE_PARAMS,
    132012: MSG_TEMPLATE_PARAMS,
    131008: MSG_TEMPLATE_PARAMS,
    131009: MSG_TEMPLATE_PARAMS,
    # The number cannot receive the message (not on WhatsApp, not allowed, our own number).
    131026: MSG_RECIPIENT_INVALID,
    131030: MSG_RECIPIENT_INVALID,
    131021: MSG_RECIPIENT_INVALID,
    # Token expired or permissions removed: an operator must act.
    0: MSG_PROVIDER_AUTH,
    3: MSG_PROVIDER_AUTH,
    10: MSG_PROVIDER_AUTH,
    190: MSG_PROVIDER_AUTH,
    200: MSG_PROVIDER_AUTH,
    131005: MSG_PROVIDER_AUTH,
}


def map_meta_error(code: object) -> str:
    try:
        number = int(str(code))
    except ValueError:
        return MSG_PROVIDER_REJECTED
    return _CODES.get(number, MSG_PROVIDER_REJECTED)
