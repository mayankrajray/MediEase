"""Booking request rules and the soft hold (M6b-P4; FR-BKG-01, 02, 06, 07; ADR-0018). Pure."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.errors import SlotHeld
from mediease_api.domain.booking.request import (
    BookingRequest,
    RequestStatus,
    newest_first,
    response_deadline,
)
from mediease_api.domain.patients.patient import Sex
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession, Session, reconcile
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.phone import PhoneNumber
from tests.builders import new_id

NOW = datetime(2026, 10, 19, 4, 0, tzinfo=UTC)
FAR = NOW + timedelta(days=3)
CLINIC, DOCTOR = new_id(), new_id()


def make(**over: object) -> BookingRequest:
    fields: dict[str, object] = {
        "id": new_id(),
        "clinic_id": CLINIC,
        "doctor_id": DOCTOR,
        "session_id": new_id(),
        "slot_start": None,
        "starts_at": FAR,
        "account_id": new_id(),
        "contact_phone": PhoneNumber.parse("9000000601"),
        "age_years": None,
        "sex": None,
        "reason": None,
        "not_emergency_ack": True,
        "requires_age_sex": False,
        "hold_minutes": 120,
        "now": NOW,
    }
    fields.update(over)
    return BookingRequest.create(**fields)  # type: ignore[arg-type]


def test_fr_bkg_06_the_deadline_is_four_hours_or_an_hour_before_the_slot() -> None:
    assert response_deadline(now=NOW, starts_at=FAR) == NOW + timedelta(hours=4)
    soon = NOW + timedelta(hours=3)
    assert response_deadline(now=NOW, starts_at=soon) == NOW + timedelta(hours=2)


def test_adr_0018_the_hold_is_two_hours_and_never_outlasts_the_deadline() -> None:
    r = make()
    assert r.hold_expires_at == NOW + timedelta(hours=2)
    assert r.respond_by == NOW + timedelta(hours=4)
    short = make(starts_at=NOW + timedelta(hours=2, minutes=30))
    assert short.respond_by == NOW + timedelta(hours=1, minutes=30)
    assert short.hold_expires_at == short.respond_by
    assert make(hold_minutes=30).hold_expires_at == NOW + timedelta(minutes=30)


def test_r6_a_slot_less_than_two_hours_away_is_refused() -> None:
    with pytest.raises(InvalidValue):
        make(starts_at=NOW + timedelta(hours=1, minutes=59))
    assert make(starts_at=NOW + timedelta(hours=2)).status is RequestStatus.PENDING


def test_r10_the_emergency_acknowledgement_is_required() -> None:
    with pytest.raises(InvalidValue):
        make(not_emergency_ack=False)


def test_r12_age_and_sex_are_required_only_when_the_clinic_says_so() -> None:
    assert make().age_years is None
    with pytest.raises(InvalidValue):
        make(requires_age_sex=True)
    with pytest.raises(InvalidValue):
        make(requires_age_sex=True, age_years=30)
    assert make(requires_age_sex=True, age_years=30, sex=Sex.FEMALE).sex is Sex.FEMALE
    with pytest.raises(InvalidValue):
        make(age_years=121)


def test_r12_the_reason_is_trimmed_and_limited_to_200_characters() -> None:
    assert make(reason="  cough  ").reason == "cough"
    with pytest.raises(InvalidValue):
        make(reason="x" * 201)


def test_hold_minutes_outside_the_range_are_refused() -> None:
    for bad in (29, 481):
        with pytest.raises(InvalidValue):
            make(hold_minutes=bad)


def test_r18a_an_override_ends_the_hold_and_keeps_the_request_pending() -> None:
    r = make()
    staff = new_id()
    assert r.is_live_hold(NOW + timedelta(minutes=1))
    r.override_hold(by=staff, now=NOW + timedelta(minutes=5))
    assert not r.is_live_hold(NOW + timedelta(minutes=5))
    assert r.status is RequestStatus.PENDING
    assert r.hold_overridden_by == staff


def test_adr_0018_a_hold_lapses_by_time_alone() -> None:
    r = make()
    assert r.is_live_hold(r.hold_expires_at - timedelta(seconds=1))
    assert not r.is_live_hold(r.hold_expires_at)


def test_newest_first_orders_by_creation() -> None:
    old, new = make(), make(now=NOW + timedelta(minutes=5))
    assert newest_first([old, new])[0] is new


# --- Appointment.book with holds -----------------------------------------------------------------

DAY = date(2026, 10, 26)
STARTS = datetime(2026, 10, 26, 4, 30, tzinfo=UTC)


def _session(mode: BookingMode, capacity: int = 2, slot: int | None = None) -> Session:
    plan = PlannedSession(DOCTOR, DAY, STARTS, STARTS + timedelta(hours=3), mode, slot, capacity)
    return Session.from_plan(plan, id=new_id(), clinic_id=CLINIC, now=NOW)


def _book(s: Session, holds: list[BookingRequest], **kw: object) -> Appointment:
    return Appointment.book(
        s,
        id=new_id(),
        patient_id=new_id(),
        active=[],
        now=NOW,
        holds=holds,
        **kw,  # type: ignore[arg-type]
    )


def test_adr_0018_a_held_slot_refuses_a_booking_and_names_when_it_lapses() -> None:
    s = _session(BookingMode.SLOTS, capacity=3, slot=60)
    held = make(slot_start=STARTS + timedelta(hours=1), starts_at=STARTS + timedelta(hours=1))
    with pytest.raises(SlotHeld) as caught:
        _book(s, [held], slot_start=STARTS + timedelta(hours=1))
    assert caught.value.details["held_until"] == held.hold_expires_at.isoformat()
    assert _book(s, [held], slot_start=STARTS).slot_start == STARTS


def test_adr_0018_tokens_are_refused_only_when_every_free_place_is_held() -> None:
    s = _session(BookingMode.TOKENS, capacity=1)
    with pytest.raises(SlotHeld):
        _book(s, [make()])
    assert _book(_session(BookingMode.TOKENS, capacity=2), [make()]) is not None


def test_a_lapsed_hold_blocks_nothing() -> None:
    s = _session(BookingMode.TOKENS, capacity=1)
    held = make(now=NOW - timedelta(days=1), starts_at=STARTS)
    assert not held.is_live_hold(NOW)
    assert _book(s, [h for h in [held] if h.is_live_hold(NOW)]) is not None


# --- reconcile with protected sessions -----------------------------------------------------------


def test_adr_0018_a_session_with_a_request_is_never_deleted_but_does_not_count_as_kept() -> None:
    s = _session(BookingMode.TOKENS)
    moved = _session(BookingMode.TOKENS, capacity=2)
    other_plan = PlannedSession(
        DOCTOR,
        DAY,
        STARTS + timedelta(hours=1),
        STARTS + timedelta(hours=2),
        BookingMode.TOKENS,
        None,
        2,
    )
    plain = reconcile([moved], [other_plan])
    assert plain.to_delete == (moved,)
    shielded = reconcile([s], [other_plan], protected={s.id})
    assert shielded.to_delete == ()
    assert shielded.to_close == (s,)
    assert shielded.kept == ()
