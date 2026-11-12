"""What a push notification says (M7e-E3, ADR-0025 decision 7; spec web-push R30-R33).

A push is shown on a lock screen, where anyone near the phone can read it. So it carries only a
fixed sentence per kind, in the person's language, and the path the notice links to. It never
names a patient, the clinic, a doctor, a time, a medicine or a reason, and it is built from the
kind alone, so there is nothing else it could say. The notice in the app stays the record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from mediease_api.domain.notifications.notification import NotificationKind
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.notifications import PatientNotificationKind

# Job payload values are at most 200 characters; a longer link falls back to the home page.
LINK_MAX = 200
PATIENT_HOME = "/portal"
STAFF_HOME = "/today"
# How long a push service keeps a message for a phone that is off (seconds). A notice about now
# (a medicine due, a patient at the desk) is useless an hour later; the rest keep for a day.
SHORT_TTL = 3600
DAY_TTL = 86_400

_OPEN = {Language.EN: "Open MediEase to see it.", Language.HI: "देखने के लिए MediEase खोलें।"}

_P = PatientNotificationKind
_PATIENT: dict[PatientNotificationKind, dict[Language, tuple[str, str]]] = {
    _P.BOOKING_ACCEPTED: {
        Language.EN: ("Booking accepted", "Your booking request was accepted."),
        Language.HI: ("बुकिंग स्वीकार हुई", "आपका बुकिंग अनुरोध स्वीकार हो गया।"),
    },
    _P.BOOKING_DECLINED: {
        Language.EN: ("Booking request answered", "Your booking request could not be booked."),
        Language.HI: ("बुकिंग अनुरोध का जवाब", "आपका बुकिंग अनुरोध बुक नहीं हो सका।"),
    },
    _P.BOOKING_PROPOSED: {
        Language.EN: ("Another time suggested", "The clinic suggested another time."),
        Language.HI: ("दूसरा समय सुझाया गया", "क्लिनिक ने दूसरा समय सुझाया है।"),
    },
    _P.BOOKING_EXPIRED: {
        Language.EN: ("Booking request expired", "Your booking request was not answered in time."),
        Language.HI: ("अनुरोध का समय निकल गया", "आपके बुकिंग अनुरोध का समय पर जवाब नहीं मिला।"),
    },
    _P.APPOINTMENT_CONFIRMED: {
        Language.EN: ("Appointment confirmed", "Your appointment is confirmed."),
        Language.HI: ("अपॉइंटमेंट पक्का", "आपका अपॉइंटमेंट पक्का हो गया है।"),
    },
    _P.APPOINTMENT_MOVED: {
        Language.EN: ("Appointment moved", "Your appointment was moved."),
        Language.HI: ("अपॉइंटमेंट बदला गया", "आपका अपॉइंटमेंट बदल दिया गया है।"),
    },
    _P.APPOINTMENT_CANCELLED: {
        Language.EN: ("Appointment cancelled", "Your appointment was cancelled."),
        Language.HI: ("अपॉइंटमेंट रद्द", "आपका अपॉइंटमेंट रद्द कर दिया गया है।"),
    },
    # A prescription or a medicine is clinical: their pushes say only that there is something new.
    _P.PRESCRIPTION_READY: {
        Language.EN: ("New from your clinic", "You have something new from your clinic."),
        Language.HI: ("क्लिनिक से नई जानकारी", "आपके क्लिनिक से नई जानकारी आई है।"),
    },
    _P.MEDICINE_DUE: {
        Language.EN: ("Reminder", "You have a reminder."),
        Language.HI: ("रिमाइंडर", "आपके लिए एक रिमाइंडर है।"),
    },
    # M7e-E4: the design's own example (decision 3).
    _P.APPOINTMENT_REMINDER: {
        Language.EN: ("Appointment reminder", "You have an upcoming appointment."),
        Language.HI: ("अपॉइंटमेंट रिमाइंडर", "आपका एक अपॉइंटमेंट आने वाला है।"),
    },
    _P.FOLLOW_UP_DUE: {
        Language.EN: ("Follow-up reminder", "It is time to book your follow-up visit."),
        Language.HI: ("फ़ॉलो-अप रिमाइंडर", "आपकी फ़ॉलो-अप विज़िट बुक करने का समय है।"),
    },
}

_S = NotificationKind
_STAFF: dict[NotificationKind, tuple[str, str]] = {
    _S.APPOINTMENT_BOOKED: ("New appointment", "An appointment was booked."),
    _S.APPOINTMENT_RESCHEDULED: ("Appointment moved", "An appointment was moved."),
    _S.APPOINTMENT_CANCELLED: ("Appointment cancelled", "An appointment was cancelled."),
    _S.PATIENT_ARRIVED: ("Patient arrived", "A patient has arrived."),
    _S.MESSAGE_FAILED: ("Message not delivered", "A message to a patient was not delivered."),
    _S.STAFF_JOINED: ("Team member joined", "Someone joined your clinic's team."),
    _S.BOOKINGS_TO_MOVE: ("Bookings to move", "Some bookings need a new time."),
    _S.BOOKING_REQUESTED: ("New booking request", "A patient asked for an appointment."),
}

_SHORT_PATIENT = frozenset({_P.MEDICINE_DUE})
_SHORT_STAFF = frozenset({_S.PATIENT_ARRIVED})
# R38: a medicine reminder comes at the time the patient chose (05:00-23:30), and a patient's
# arrival happens only while the clinic is open, so their pushes never wait for the quiet hours.
# (The in-app notice never waits at all: decision 7A, ``KINDS[...].respects_quiet_hours``.)
_ANYTIME: frozenset[PatientNotificationKind | NotificationKind] = frozenset(
    {_P.MEDICINE_DUE, _S.PATIENT_ARRIVED}
)


def waits_for_quiet_hours(kind: PatientNotificationKind | NotificationKind) -> bool:
    """R38: whether a push of this kind is held until the clinic's quiet hours end (08:00)."""
    return kind not in _ANYTIME


@dataclass(frozen=True, slots=True)
class PushMessage:
    """The JSON the service worker shows: a title, a body, the path to open, and a tag.

    ``tag`` is the kind, so a newer notice of the same kind replaces the older one on the screen
    instead of stacking. ``ttl`` is not sent in the body: it is the push service's keep time.
    """

    title: str
    body: str
    url: str
    tag: str
    ttl: int

    def encode(self) -> str:
        return json.dumps(
            {"title": self.title, "body": self.body, "url": self.url, "tag": self.tag},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def safe_link(link: str | None, home: str) -> str:
    """A same-site path of at most ``LINK_MAX`` characters, else ``home``."""
    if (
        link is None
        or not link.startswith("/")
        or link.startswith("//")
        or "\\" in link
        or len(link) > LINK_MAX
    ):
        return home
    return link


def patient_message(kind: PatientNotificationKind, lang: Language, link: str | None) -> PushMessage:
    title, line = _PATIENT[kind][lang]
    link = safe_link(link, PATIENT_HOME)
    if not link.startswith(PATIENT_HOME):
        link = PATIENT_HOME
    return PushMessage(
        title=title,
        body=f"{line} {_OPEN[lang]}",
        url=link,
        tag=kind.value,
        ttl=SHORT_TTL if kind in _SHORT_PATIENT else DAY_TTL,
    )


def staff_message(kind: NotificationKind, link: str | None) -> PushMessage:
    """Staff read English (M6a); the notice in the app has the names."""
    title, line = _STAFF[kind]
    return PushMessage(
        title=title,
        body=f"{line} {_OPEN[Language.EN]}",
        url=safe_link(link, STAFF_HOME),
        tag=kind.value,
        ttl=SHORT_TTL if kind in _SHORT_STAFF else DAY_TTL,
    )
