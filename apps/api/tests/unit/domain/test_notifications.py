"""Notifications and the typed title catalogue (M6a-P7; FR-NTF-06, ADR-0017 decision 4A)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mediease_api.domain.notifications.notification import (
    KINDS,
    TITLE_MAX,
    Channel,
    Notification,
    NotificationKind,
    PatientRef,
    PersonName,
    Place,
    RoleLabel,
    arrived_title,
    booked_title,
    cancelled_title,
    ensure_in_app,
    message_failed_title,
    queue_link,
    rescheduled_title,
    staff_joined_title,
)
from mediease_api.domain.shared.errors import InvalidTransition, InvalidValue
from tests.builders import NOW, new_id

# 05:00 UTC is 10:30 in Kolkata, on the same day.
MORNING = datetime(2026, 10, 23, 5, 0, tzinfo=UTC)


def test_fr_ntf_06_a_patient_is_first_name_and_code_only() -> None:
    assert str(PatientRef.of("Asha Kumari Rao", "ME-0142")) == "Asha · ME-0142"
    assert str(PatientRef.of("   ", "ME-0001")) == "Patient · ME-0001"
    assert len(PatientRef.of("A" * 100, "ME-0002").first_name) == 40


def test_a_place_is_the_day_and_the_token_or_the_clinic_time() -> None:
    assert Place.of(starts_at=MORNING, token_number=4, timezone="Asia/Kolkata").text == (
        "23 Oct, token 4"
    )
    assert Place.of(starts_at=MORNING, token_number=None, timezone="Asia/Kolkata").text == (
        "23 Oct, 10:30"
    )
    late = MORNING + timedelta(hours=14)  # 00:30 the next day in Kolkata
    assert Place.of(starts_at=late, token_number=None, timezone="Asia/Kolkata").text == (
        "24 Oct, 00:30"
    )
    with pytest.raises(InvalidValue):
        Place.of(starts_at=MORNING.replace(tzinfo=None), token_number=1, timezone="Asia/Kolkata")


def test_fr_ntf_06_titles_are_built_from_typed_values() -> None:
    patient = PatientRef("Asha", "ME-0142")
    place = Place("23 Oct, token 4")
    assert booked_title(patient, place) == "Asha · ME-0142 booked for 23 Oct, token 4"
    assert rescheduled_title(patient, place) == "Asha · ME-0142 moved to 23 Oct, token 4"
    assert cancelled_title(patient, place) == "Asha · ME-0142 cancelled for 23 Oct, token 4"
    assert arrived_title(patient, place) == "Asha · ME-0142 has arrived (23 Oct, token 4)"
    assert message_failed_title(patient) == "A message to Asha · ME-0142 could not be delivered"
    joined = staff_joined_title(PersonName("N" * 200), RoleLabel("a doctor"))
    assert joined == f"{'N' * 80} joined the team as a doctor"
    assert len(joined) <= TITLE_MAX
    assert queue_link(date(2026, 10, 23)) == "/queue?date=2026-10-23"


def test_every_kind_has_a_label_and_in_app_ignores_quiet_hours() -> None:
    assert set(KINDS) == set(NotificationKind)
    assert all(info.label and not info.respects_quiet_hours for info in KINDS.values())


def _notification(**overrides: object) -> Notification:
    fields: dict[str, object] = {
        "id": new_id(),
        "clinic_id": new_id(),
        "recipient_user_id": new_id(),
        "kind": NotificationKind.APPOINTMENT_BOOKED,
        "event_key": "appointment.booked:x",
        "title": "Asha · ME-0142 booked for 23 Oct, token 4",
        "link": "/queue?date=2026-10-23",
        "entity_type": "appointment",
        "entity_id": new_id(),
        "now": NOW,
    }
    fields.update(overrides)
    return Notification.create(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", ""),
        ("title", "x" * (TITLE_MAX + 1)),
        ("link", "https://elsewhere.example/queue"),
        ("link", "//elsewhere.example"),
        ("link", "/" + "x" * 200),
        ("event_key", ""),
        ("now", NOW.replace(tzinfo=None)),
    ],
)
def test_a_notification_is_validated(field: str, value: object) -> None:
    with pytest.raises(InvalidValue):
        _notification(**{field: value})


def test_reading_twice_keeps_the_first_time() -> None:
    notification = _notification()
    assert not notification.is_read
    assert notification.mark_read(NOW) is True
    assert notification.mark_read(NOW + timedelta(minutes=5)) is False
    assert notification.read_at == NOW and notification.is_read


def test_staff_choose_in_app_only() -> None:
    ensure_in_app(Channel.IN_APP)
    for channel in (Channel.WHATSAPP, Channel.EMAIL, Channel.SMS):
        with pytest.raises(InvalidTransition):
            ensure_in_app(channel)
