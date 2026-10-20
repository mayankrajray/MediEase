"""The messaging job kinds and their keys (M5-P2; spec R6, R9c; FR-APT-06, prescriptions R15).

The job's ``dedupe_key`` and the message's ``idempotency_key`` are the same string, so one
appointment or prescription version is confirmed at most once however often it is enqueued.
"""

from __future__ import annotations

from uuid import UUID

BOOKING_CONFIRMATION_KIND = "send_booking_confirmation"
RX_LINK_KIND = "send_rx_link"
# M5-P4: a follow-up reminder (one job per reminder revision, decision 1A).
REMINDER_KIND = "send_reminder"
# M5-P5: one SMS after a reminder's WhatsApp message failed (FR-REM-06, decision 4A).
SMS_FALLBACK_KIND = "send_sms_fallback"
# M5-P5: the reply to a STOP, one per clinic that opted the sender out (decision 3A).
OPT_OUT_CONFIRMATION_KIND = "send_opt_out_confirmation"

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


def reminder_message_key(reminder_id: UUID) -> str:
    """One message per reminder, however many jobs its moves made."""
    return f"{FOLLOW_UP_DUE}:{reminder_id}"


def reminder_job_key(reminder_id: UUID, revision: int) -> str:
    return f"reminder:{reminder_id}:{revision}"


def opt_out_confirmation_key(clinic_id: UUID, inbound_message_id: str) -> str:
    """At most one reply per STOP message per clinic (M5-P5 decision 3A)."""
    return f"{OPT_OUT_CONFIRMED}:{clinic_id}:{inbound_message_id}"


def sms_fallback_key(reminder_id: UUID) -> str:
    """The SMS message of a reminder: at most one, however often its job is deferred."""
    return f"sms:{reminder_id}"


def sms_fallback_job_key(reminder_id: UUID, deferrals: int) -> str:
    """Each deferral out of the quiet hours is a fresh job (P4 decision 2A)."""
    return f"sms_fallback:{reminder_id}:{deferrals}"
