"""Notifications, their kinds and channels, and the typed title catalogue (M6a-P7).

**Titles are built only from typed values** (decision 4A, FR-NTF-06, FR-MSG-04): a patient as
"first name · code", a doctor's name, a place in the day, a role. There is no free-text value and
no clinical type, so a title cannot carry a complaint, a diagnosis or a medicine. English at MVP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from mediease_api.domain.shared.time import require_utc

TITLE_MAX = 160
LINK_MAX = 200


class NotificationKind(StrEnum):
    """What a staff member can be notified of in the app (each one a preference)."""

    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    PATIENT_ARRIVED = "appointment.arrived"
    MESSAGE_FAILED = "message.failed"
    STAFF_JOINED = "staff.joined"


class Channel(StrEnum):
    IN_APP = "IN_APP"
    WHATSAPP = "WHATSAPP"
    # Declared for preferences; nothing delivers by them yet (ADR-0017 decision 2).
    EMAIL = "EMAIL"
    SMS = "SMS"


@dataclass(frozen=True, slots=True)
class KindInfo:
    label: str
    # Decision 7A: in-app ignores quiet hours; a kind sent outside the app later may obey them.
    respects_quiet_hours: bool = False


KINDS: dict[NotificationKind, KindInfo] = {
    NotificationKind.APPOINTMENT_BOOKED: KindInfo("A patient is booked with me"),
    NotificationKind.APPOINTMENT_RESCHEDULED: KindInfo("A booking with me is moved"),
    NotificationKind.APPOINTMENT_CANCELLED: KindInfo("A booking with me is cancelled"),
    NotificationKind.PATIENT_ARRIVED: KindInfo("My patient has arrived"),
    NotificationKind.MESSAGE_FAILED: KindInfo("A message to a patient failed"),
    NotificationKind.STAFF_JOINED: KindInfo("Someone joined the team"),
}


# --- The typed values a title may hold ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PatientRef:
    """A patient as staff see them at a glance: first name and code (as on Today)."""

    first_name: str
    code: str

    @classmethod
    def of(cls, full_name: str, code: str) -> PatientRef:
        first = (full_name.split() or ["Patient"])[0][:40]
        return cls(first_name=first, code=code)

    def __str__(self) -> str:
        return f"{self.first_name} · {self.code}"


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True, slots=True)
class Place:
    """When in the day: ``23 Oct, token 4`` or ``23 Oct, 10:30`` on the clinic's clock."""

    text: str

    @classmethod
    def of(cls, *, starts_at: datetime, token_number: int | None, timezone: str) -> Place:
        local = require_utc(starts_at, "starts_at").astimezone(ZoneInfo(timezone))
        day = f"{local.day} {_MONTHS[local.month - 1]}"
        if token_number is not None:
            return cls(f"{day}, token {token_number}")
        return cls(f"{day}, {local.hour:02d}:{local.minute:02d}")


@dataclass(frozen=True, slots=True)
class PersonName:
    """A staff member's name, as on the Team page."""

    text: str


@dataclass(frozen=True, slots=True)
class RoleLabel:
    text: str


def booked_title(patient: PatientRef, place: Place) -> str:
    return f"{patient} booked for {place.text}"


def rescheduled_title(patient: PatientRef, place: Place) -> str:
    return f"{patient} moved to {place.text}"


def cancelled_title(patient: PatientRef, place: Place) -> str:
    return f"{patient} cancelled for {place.text}"


def arrived_title(patient: PatientRef, place: Place) -> str:
    return f"{patient} has arrived ({place.text})"


def message_failed_title(patient: PatientRef) -> str:
    return f"A message to {patient} could not be delivered"


def staff_joined_title(person: PersonName, role: RoleLabel) -> str:
    return f"{person.text[:80]} joined the team as {role.text}"


def queue_link(on_date: date) -> str:
    return f"/queue?date={on_date.isoformat()}"


# --- The notification -------------------------------------------------------------------------


@dataclass(slots=True)
class Notification:
    """One in-app notification for one staff member. Build with ``create``."""

    id: UUID
    clinic_id: UUID
    recipient_user_id: UUID
    kind: NotificationKind
    # Idempotency (FR-NTF-06): one per recipient and event, whatever the replays.
    event_key: str
    title: str
    link: str
    entity_type: str
    entity_id: UUID
    created_at: datetime
    read_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        recipient_user_id: UUID,
        kind: NotificationKind,
        event_key: str,
        title: str,
        link: str,
        entity_type: str,
        entity_id: UUID,
        now: datetime,
    ) -> Notification:
        if not 1 <= len(title) <= TITLE_MAX:
            raise InvalidValue("title", f"must be 1-{TITLE_MAX} characters")
        if not link.startswith("/") or link.startswith("//") or len(link) > LINK_MAX:
            raise InvalidValue("link", "must be a path inside the app")
        if not 1 <= len(event_key) <= 200:
            raise InvalidValue("event_key", "must be 1-200 characters")
        return cls(
            id=id,
            clinic_id=clinic_id,
            recipient_user_id=recipient_user_id,
            kind=kind,
            event_key=event_key,
            title=title,
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
            created_at=require_utc(now, "now"),
        )

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self, now: datetime) -> bool:
        """True when this changed it (reading twice keeps the first time)."""
        if self.read_at is not None:
            return False
        self.read_at = require_utc(now, "now")
        return True


@dataclass(frozen=True, slots=True)
class Preference:
    """A member's choice for one kind and channel; absent means the default (on)."""

    user_id: UUID
    kind: NotificationKind
    channel: Channel
    enabled: bool


def ensure_in_app(channel: Channel) -> None:
    """Staff choose in-app only in M6a (decision 5A); other channels are not offered yet."""
    if channel is not Channel.IN_APP:
        raise InvalidTransition("notification preference", channel.value, "change")
