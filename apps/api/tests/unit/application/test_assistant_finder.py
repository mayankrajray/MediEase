"""The patient assistant's word-to-record helpers (M7c-P7; spec assistant R22-R25)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest

from mediease_api.application.assistant.finder import (
    Named,
    clock,
    find_offer,
    in_part,
    part_of_day,
    pick,
    resolve_doctor,
)
from mediease_api.application.assistant.tools import ToolArgumentError
from mediease_api.application.booking.public import (
    DayOffer,
    PublicDoctor,
    SessionOffer,
    SlotOffer,
)
from mediease_api.domain.scheduling.mode import BookingMode

CLINICS = [
    Named("alpha", "Sample Clinic"),
    Named("alpha-two", "Sample Clinic Two"),
    Named("family", "Sample Family Clinic"),
]


def test_r23_an_exact_name_wins_and_several_matches_are_a_question() -> None:
    assert pick("sample clinic", CLINICS, "clinic").key == "alpha"
    assert pick("alpha-two", CLINICS, "clinic").key == "alpha-two"
    assert pick("family", CLINICS, "clinic").key == "family"
    with pytest.raises(ToolArgumentError, match="more than one clinic"):
        pick("sample", CLINICS, "clinic")
    with pytest.raises(ToolArgumentError, match="no clinic called"):
        pick("Nowhere", CLINICS, "clinic")


def _doctor(n: int, name: str) -> PublicDoctor:
    return PublicDoctor(UUID(int=n), name, "MBBS", None, ())


def test_r23_a_doctor_by_name_without_dr_or_the_only_one() -> None:
    one = [_doctor(1, "Dr. Sample Doctor")]
    assert resolve_doctor(one, None).id == UUID(int=1)
    assert resolve_doctor(one, "sample doctor").id == UUID(int=1)
    two = [*one, _doctor(2, "Dr. Other Doctor")]
    assert resolve_doctor(two, str(UUID(int=2))).id == UUID(int=2)
    with pytest.raises(ToolArgumentError, match="more than one doctor"):
        resolve_doctor(two, None)


def test_r24_parts_of_the_day_and_clock_times_in_english_and_hinglish() -> None:
    assert part_of_day("Subah") == "morning" and part_of_day("dopahar") == "afternoon"
    assert part_of_day("शाम") == "evening" and part_of_day(None) is None
    with pytest.raises(ToolArgumentError):
        part_of_day("midnight-ish")
    assert in_part(time(11, 59), "morning") and not in_part(time(12, 0), "morning")
    assert in_part(time(16, 59), "afternoon") and in_part(time(17, 0), "evening")
    assert clock("10:00") == time(10) and clock("4:30 PM") == time(16, 30)
    assert clock("12:15 am") == time(0, 15) and clock("16.30") == time(16, 30)
    with pytest.raises(ToolArgumentError):
        clock("ten")


def _at(hour: int, minute: int = 0) -> datetime:
    # 05:30 UTC is 11:00 in India.
    return datetime(2026, 11, 12, hour, minute, tzinfo=UTC)


def test_r24_a_time_is_found_only_while_it_is_free() -> None:
    day = date(2026, 11, 12)
    slots = SessionOffer(
        _at(4, 30), _at(7, 30), BookingMode.SLOTS, 2, (SlotOffer(_at(4, 30), _at(4, 45)),)
    )
    tokens = SessionOffer(_at(11, 30), _at(13, 30), BookingMode.TOKENS, 5, ())
    days = [DayOffer(day, (slots, tokens))]
    found = find_offer(days, day, time(10, 0), "Asia/Kolkata")
    assert found is not None and found.slot_start == _at(4, 30)
    assert find_offer(days, day, time(10, 15), "Asia/Kolkata") is None  # not a free slot
    inside = find_offer(days, day, time(17, 30), "Asia/Kolkata")  # in the 17:00-19:00 tokens
    assert inside is not None and inside.slot_start is None and inside.session_start == _at(11, 30)
    assert find_offer(days, date(2026, 11, 13), time(10, 0), "Asia/Kolkata") is None
