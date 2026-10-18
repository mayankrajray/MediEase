"""The messaging job kinds and their keys (M5-P2; spec R6, R9c; FR-APT-06, prescriptions R15).

The job's ``dedupe_key`` and the message's ``idempotency_key`` are the same string, so one
appointment or prescription version is confirmed at most once however often it is enqueued.
"""

from __future__ import annotations

from uuid import UUID

BOOKING_CONFIRMATION_KIND = "send_booking_confirmation"
RX_LINK_KIND = "send_rx_link"

BOOKING_CONFIRMED = "booking_confirmed"
RX_READY = "rx_ready"
RX_UPDATED = "rx_updated"
FOLLOW_UP_DUE = "follow_up_due"
OPT_OUT_CONFIRMED = "opt_out_confirmed"

# Every template the code sends; the loader refuses a templates file without one of them.
REQUIRED_TEMPLATES = frozenset(
    {BOOKING_CONFIRMED, RX_READY, RX_UPDATED, FOLLOW_UP_DUE, OPT_OUT_CONFIRMED}
)


def booking_confirmation_key(appointment_id: UUID) -> str:
    return f"{BOOKING_CONFIRMED}:{appointment_id}"


def rx_link_key(prescription_id: UUID) -> str:
    return f"rx_link:{prescription_id}"
