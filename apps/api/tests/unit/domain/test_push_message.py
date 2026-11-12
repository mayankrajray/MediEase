"""M7e-E3 (spec web-push R32, R33): what a push says. Fixed words per kind; no names, no times."""

from __future__ import annotations

import json

import pytest

from mediease_api.domain.notifications.notification import NotificationKind
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.notifications import PatientNotificationKind
from mediease_api.domain.push.message import (
    DAY_TTL,
    LINK_MAX,
    PATIENT_HOME,
    SHORT_TTL,
    STAFF_HOME,
    patient_message,
    safe_link,
    staff_message,
    waits_for_quiet_hours,
)

_DIGITS = set("0123456789")


@pytest.mark.parametrize("kind", list(PatientNotificationKind))
@pytest.mark.parametrize("lang", list(Language))
def test_r32_every_patient_kind_has_fixed_words_in_both_languages(
    kind: PatientNotificationKind, lang: Language
) -> None:
    message = patient_message(kind, lang, "/portal/appointments")
    assert message.title and message.body
    # Nothing that could be a time, a token, a phone or a count.
    assert not _DIGITS & set(message.title + message.body)
    assert json.loads(message.encode()) == {
        "title": message.title,
        "body": message.body,
        "url": "/portal/appointments",
        "tag": kind.value,
    }


@pytest.mark.parametrize("kind", list(NotificationKind))
def test_r32_every_staff_kind_has_fixed_words(kind: NotificationKind) -> None:
    message = staff_message(kind, "/today")
    assert message.title and message.body.endswith("Open MediEase to see it.")
    assert not _DIGITS & set(message.title + message.body)


def test_r32_clinical_kinds_say_only_that_something_is_new() -> None:
    for kind in (PatientNotificationKind.PRESCRIPTION_READY, PatientNotificationKind.MEDICINE_DUE):
        words = patient_message(kind, Language.EN, None)
        text = (words.title + words.body).lower()
        assert "prescription" not in text and "medicine" not in text


def test_r33_hindi_is_hindi() -> None:
    words = patient_message(PatientNotificationKind.APPOINTMENT_CANCELLED, Language.HI, None)
    assert words.title == "अपॉइंटमेंट रद्द"
    assert "Open" not in words.body
    assert "रद्द" in json.loads(words.encode())["title"]  # not escaped away


@pytest.mark.parametrize(
    "link",
    [
        None,
        "",
        "portal",
        "//evil.example/x",
        "https://evil.example/",
        "/\\evil",
        "/" + "a" * LINK_MAX,
    ],
)
def test_r32_a_link_is_a_short_same_site_path_or_home(link: str | None) -> None:
    assert safe_link(link, "/home") == "/home"


def test_r32_a_patient_push_opens_only_portal_paths() -> None:
    assert patient_message(PatientNotificationKind.BOOKING_ACCEPTED, Language.EN, "/today").url == (
        PATIENT_HOME
    )
    rx = "/portal/prescriptions/0190a8b0-0000-7000-8000-000000000001"
    assert patient_message(PatientNotificationKind.PRESCRIPTION_READY, Language.EN, rx).url == rx
    assert staff_message(NotificationKind.STAFF_JOINED, None).url == STAFF_HOME


def test_r32_notices_about_now_keep_an_hour_the_rest_a_day() -> None:
    assert patient_message(PatientNotificationKind.MEDICINE_DUE, Language.EN, None).ttl == SHORT_TTL
    assert staff_message(NotificationKind.PATIENT_ARRIVED, None).ttl == SHORT_TTL
    assert staff_message(NotificationKind.BOOKING_REQUESTED, None).ttl == DAY_TTL


def test_r38_only_the_medicine_reminder_and_an_arrival_ignore_the_quiet_hours() -> None:
    waiting = {k for k in PatientNotificationKind if waits_for_quiet_hours(k)}
    assert waiting == set(PatientNotificationKind) - {PatientNotificationKind.MEDICINE_DUE}
    staff = {k for k in NotificationKind if waits_for_quiet_hours(k)}
    assert staff == set(NotificationKind) - {NotificationKind.PATIENT_ARRIVED}
