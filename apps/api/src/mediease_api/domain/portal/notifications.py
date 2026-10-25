"""Patient notifications (M6b-P6; FR-NTF-01, 04, 05, 06; portal spec R55-R68).

``patient_notifications`` holds **one row per notification**, each belonging to one account and
one clinic. No text is stored: ``params`` holds IDs, a time, a token, a slot or a decline reason
code, and the title is rendered on read in the account's language (R55), so switching to Hindi
changes past notices too. ``(account_id, event_key)`` is unique in the database: a replayed or
concurrent event inserts nothing (R58).

A title never holds a diagnosis, medicine, dose, reason text, staff note, phone or age (R59):
only the clinic's name, the doctor's display name, a day and time or token, a slot, and the
decline reason's patient words.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID
from zoneinfo import ZoneInfo

from mediease_api.domain.booking.request import DeclineReason
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

LINK_MAX = 300
EVENT_KEY_MAX = 200
PARAM_KEYS = frozenset({"at", "token", "doctor_id", "reason", "slot", "time"})


class PatientNotificationKind(StrEnum):
    """R57: what a patient can be told. Each kind can be turned off (R62)."""

    BOOKING_ACCEPTED = "booking.accepted"
    BOOKING_DECLINED = "booking.declined"
    BOOKING_PROPOSED = "booking.proposed"
    BOOKING_EXPIRED = "booking.expired"
    APPOINTMENT_CONFIRMED = "appointment.confirmed"
    APPOINTMENT_MOVED = "appointment.moved"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    PRESCRIPTION_READY = "prescription.ready"
    MEDICINE_DUE = "medicine.due"


# R63: the only kinds that may also go by email.
BOOKING_KINDS: frozenset[PatientNotificationKind] = frozenset(
    {
        PatientNotificationKind.BOOKING_ACCEPTED,
        PatientNotificationKind.BOOKING_DECLINED,
        PatientNotificationKind.BOOKING_PROPOSED,
        PatientNotificationKind.BOOKING_EXPIRED,
    }
)


class PatientChannel(StrEnum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"


def check_channel(kind: PatientNotificationKind, channel: PatientChannel) -> None:
    """R62, R63: every kind in the app; email for the four booking kinds only."""
    if channel is PatientChannel.EMAIL and kind not in BOOKING_KINDS:
        raise InvalidValue("channel", "email is only for booking answers")


@dataclass(slots=True)
class PatientNotification:
    """One notice for one account. Build with ``create``; the constructor rehydrates."""

    id: UUID
    clinic_id: UUID
    account_id: UUID
    kind: PatientNotificationKind
    event_key: str
    entity_type: str
    entity_id: UUID
    link: str
    params: Mapping[str, str]
    created_at: datetime
    read_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        account_id: UUID,
        kind: PatientNotificationKind,
        event_key: str,
        entity: tuple[str, UUID],
        link: str,
        params: Mapping[str, str],
        now: datetime,
    ) -> PatientNotification:
        if not link.startswith("/portal") or link.startswith("//") or len(link) > LINK_MAX:
            raise InvalidValue("link", "must be a portal path")
        if not 1 <= len(event_key) <= EVENT_KEY_MAX:
            raise InvalidValue("event_key", f"must be 1-{EVENT_KEY_MAX} characters")
        unknown = set(params) - PARAM_KEYS
        if unknown:
            raise InvalidValue("params", "holds IDs, a time, a token, a slot or a reason only")
        return cls(
            id=id,
            clinic_id=clinic_id,
            account_id=account_id,
            kind=kind,
            event_key=event_key,
            entity_type=entity[0],
            entity_id=entity[1],
            link=link,
            params=MappingProxyType(dict(params)),
            created_at=require_utc(now, "now"),
        )

    def mark_read(self, now: datetime) -> bool:
        if self.read_at is not None:
            return False
        self.read_at = require_utc(now, "now")
        return True


# --- Rendering (R55, R59) ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Names:
    """What a title may name, read from the clinic's own rows when the list is read."""

    clinic: str
    doctor: str | None
    timezone: str


_MONTHS = {
    Language.EN: (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ),
    Language.HI: (
        "जन॰",
        "फ़र॰",
        "मार्च",
        "अप्रैल",
        "मई",
        "जून",
        "जुल॰",
        "अग॰",
        "सित॰",
        "अक्टू॰",
        "नव॰",
        "दिस॰",
    ),
}
_SLOTS = {
    Language.EN: {
        "MORNING": "Morning",
        "AFTERNOON": "Afternoon",
        "EVENING": "Evening",
        "NIGHT": "Night",
    },
    Language.HI: {"MORNING": "सुबह", "AFTERNOON": "दोपहर", "EVENING": "शाम", "NIGHT": "रात"},
}
# The decline reason's patient words (P5 R49), in the app only (never in an email, R63).
_REASONS = {
    Language.EN: {
        DeclineReason.TIME_UNAVAILABLE: "that time is no longer available",
        DeclineReason.DOCTOR_UNAVAILABLE: "the doctor is not available then",
        DeclineReason.PLEASE_CALL: "please call the clinic",
        DeclineReason.NOT_ONLINE: "this cannot be booked online",
        DeclineReason.DUPLICATE: "you already have a request or booking for this",
        DeclineReason.OTHER: "the clinic could not book this time",
        DeclineReason.PATIENT_DECLINED: "you said no thanks",
        DeclineReason.CLINIC_UNAVAILABLE: "the clinic is not taking online bookings now",
    },
    Language.HI: {
        DeclineReason.TIME_UNAVAILABLE: "वह समय अब उपलब्ध नहीं है",
        DeclineReason.DOCTOR_UNAVAILABLE: "उस समय डॉक्टर उपलब्ध नहीं हैं",
        DeclineReason.PLEASE_CALL: "कृपया क्लिनिक को फ़ोन करें",
        DeclineReason.NOT_ONLINE: "इसे ऑनलाइन बुक नहीं किया जा सकता",
        DeclineReason.DUPLICATE: "इसके लिए आपका अनुरोध या बुकिंग पहले से है",
        DeclineReason.OTHER: "क्लिनिक यह समय बुक नहीं कर सका",
        DeclineReason.PATIENT_DECLINED: "आपने मना कर दिया",
        DeclineReason.CLINIC_UNAVAILABLE: "क्लिनिक अभी ऑनलाइन बुकिंग नहीं ले रहा है",
    },
}


def _when(params: Mapping[str, str], names: Names, lang: Language) -> str:
    raw = params.get("at")
    if raw is None:
        return ""
    local = datetime.fromisoformat(raw).astimezone(ZoneInfo(names.timezone))
    day = f"{local.day} {_MONTHS[lang][local.month - 1]}"
    token = params.get("token")
    if token is not None:
        return f"{day}, {'टोकन' if lang is Language.HI else 'token'} {token}"
    return f"{day}, {local.hour:02d}:{local.minute:02d}"


def decline_words(reason: str | None, lang: Language) -> str:
    try:
        return _REASONS[lang][DeclineReason(reason or "OTHER")]
    except ValueError:
        return _REASONS[lang][DeclineReason.OTHER]


def render_title(n: PatientNotification, names: Names, lang: Language) -> str:
    """R55, R59: the title in the account's language, from typed values only."""
    k = PatientNotificationKind
    when = _when(n.params, names, lang)
    clinic = names.clinic[:80]
    doctor = (names.doctor or "")[:80]
    hi = lang is Language.HI
    match n.kind:
        case k.BOOKING_ACCEPTED:
            return (
                f"बुक हो गया: {when}, {doctor} ({clinic})"
                if hi
                else f"Booked: {when} with {doctor} at {clinic}"
            )
        case k.BOOKING_DECLINED:
            words = decline_words(n.params.get("reason"), lang)
            return (
                f"{clinic}: अनुरोध नहीं हो सका, {words}"
                if hi
                else f"{clinic} declined your request: {words}"
            )
        case k.BOOKING_PROPOSED:
            return (
                f"{clinic} ने दूसरा समय सुझाया: {when}"
                if hi
                else f"{clinic} suggests another time: {when}"
            )
        case k.BOOKING_EXPIRED:
            return (
                f"{clinic} ने समय पर जवाब नहीं दिया"
                if hi
                else f"{clinic} did not reply to your request in time"
            )
        case k.APPOINTMENT_CONFIRMED:
            return (
                f"अपॉइंटमेंट पक्का: {when}, {doctor}"
                if hi
                else f"Appointment confirmed: {when} with {doctor}"
            )
        case k.APPOINTMENT_MOVED:
            return (
                f"अपॉइंटमेंट बदला गया: {when}, {doctor}"
                if hi
                else f"Appointment moved to {when} with {doctor}"
            )
        case k.APPOINTMENT_CANCELLED:
            return (
                f"{clinic} ने {when} की अपॉइंटमेंट रद्द की"
                if hi
                else f"{clinic} cancelled your appointment on {when}"
            )
        case k.PRESCRIPTION_READY:
            return f"{doctor} का नया पर्चा" if hi else f"New prescription from {doctor}"
        case k.MEDICINE_DUE:
            slot = _SLOTS[lang].get(n.params.get("slot", ""), "")
            time = n.params.get("time", "")
            return f"{slot} की दवाइयाँ · {time}" if hi else f"{slot} medicines · {time}"
    return ""  # pragma: no cover - every kind is matched


@dataclass(frozen=True, slots=True)
class EmailWords:
    subject: str
    text: str


def booking_email(
    kind: PatientNotificationKind, names: Names, lang: Language, link: str
) -> EmailWords:
    """R63: the clinic and the outcome, and the portal link; never the reason or the note."""
    clinic = names.clinic[:80]
    hi = lang is Language.HI
    subject = {
        PatientNotificationKind.BOOKING_ACCEPTED: ("बुकिंग पक्की", "Booking confirmed"),
        PatientNotificationKind.BOOKING_DECLINED: ("बुकिंग नहीं हो सकी", "Booking declined"),
        PatientNotificationKind.BOOKING_PROPOSED: ("दूसरा समय सुझाया गया", "Another time suggested"),
        PatientNotificationKind.BOOKING_EXPIRED: ("अनुरोध का समय निकल गया", "Request expired"),
    }[kind]
    head = f"{subject[0]}: {clinic}" if hi else f"{subject[1]} at {clinic}"
    body = (
        f"{head}\n\nविवरण देखने के लिए MediEase में खोलें: {link}\n"
        if hi
        else f"{head}.\n\nOpen MediEase to see the details: {link}\n"
    )
    return EmailWords(subject=f"{head} · MediEase", text=body)


__all__ = [
    "BOOKING_KINDS",
    "EmailWords",
    "Names",
    "PatientChannel",
    "PatientNotification",
    "PatientNotificationKind",
    "booking_email",
    "check_channel",
    "decline_words",
    "render_title",
]
