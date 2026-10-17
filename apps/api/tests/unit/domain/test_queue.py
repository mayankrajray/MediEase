"""Queue rules (FR-QUE-02; spec R9-R11, AC3; decisions D18-D21). Pure."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.errors import InvalidQueueTransition, WrongTime
from mediease_api.domain.appointments.queue import (
    TRANSITIONS,
    first_free_slot,
    is_session_day,
    transition,
    wait_minutes,
)
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession, Session
from tests.builders import new_id

S = AppointmentStatus
ON = date(2026, 10, 19)
STARTS = datetime(2026, 10, 19, 4, 30, tzinfo=UTC)  # 10:00 Kolkata
ENDS = STARTS + timedelta(hours=3)
DURING = STARTS + timedelta(minutes=20)
BEFORE = STARTS - timedelta(hours=2)


def session(mode: BookingMode = BookingMode.TOKENS, *, starts: datetime = STARTS) -> Session:
    slot = 60 if mode is BookingMode.SLOTS else None
    plan = PlannedSession(new_id(), ON, starts, starts + timedelta(hours=3), mode, slot, 3)
    return Session.from_plan(plan, id=new_id(), clinic_id=new_id(), now=BEFORE - timedelta(days=1))


def booked(s: Session, slot: datetime | None = None) -> Appointment:
    return Appointment.book(
        s,
        id=new_id(),
        patient_id=new_id(),
        active=[],
        now=BEFORE - timedelta(days=1),
        slot_start=slot,
    )


def move(a: Appointment, s: Session, seen: S, to: S, now: datetime = DURING) -> S:
    return transition(a, s, seen=seen, to=to, now=now, today=ON)


def test_fr_que_02_the_happy_path_sets_each_timestamp() -> None:
    s = session()
    a = booked(s)
    assert move(a, s, S.BOOKED, S.ARRIVED, BEFORE) is S.BOOKED
    assert a.arrived_at == BEFORE
    move(a, s, S.ARRIVED, S.IN_CONSULTATION)
    move(a, s, S.IN_CONSULTATION, S.COMPLETED, DURING + timedelta(minutes=10))
    assert (a.status, a.started_at, a.completed_at) == (
        S.COMPLETED,
        DURING,
        DURING + timedelta(minutes=10),
    )
    assert a.updated_at == DURING + timedelta(minutes=10)


def test_ac3_completed_to_arrived_is_refused_with_from_and_to() -> None:
    s = session()
    a = booked(s)
    a.status = S.COMPLETED
    with pytest.raises(InvalidQueueTransition) as raised:
        move(a, s, S.COMPLETED, S.ARRIVED)
    assert raised.value.details == {"from": "COMPLETED", "to": "ARRIVED"}


@pytest.mark.parametrize("current", list(S))
@pytest.mark.parametrize("to", list(S))
def test_r9_only_the_state_machines_edges_are_allowed(current: S, to: S) -> None:
    s = session()
    a = booked(s)
    a.status = current
    if to in TRANSITIONS[current]:
        move(a, s, current, to)
        assert a.status is to
    else:
        with pytest.raises(InvalidQueueTransition):
            move(a, s, current, to)
    assert S.CANCELLED not in set().union(*TRANSITIONS.values())


def test_d18_a_stale_screen_gets_the_real_status() -> None:
    s = session()
    a = booked(s)
    move(a, s, S.BOOKED, S.ARRIVED)
    with pytest.raises(InvalidQueueTransition) as raised:
        move(a, s, S.BOOKED, S.NO_SHOW)  # the other tab still shows BOOKED
    assert raised.value.details == {"from": "ARRIVED", "to": "NO_SHOW"}
    assert a.status is S.ARRIVED


def test_d19_the_queue_moves_on_the_sessions_day_only() -> None:
    s = session()
    a = booked(s)
    with pytest.raises(WrongTime) as raised:
        day_before = DURING - timedelta(days=1)
        transition(a, s, seen=S.BOOKED, to=S.ARRIVED, now=day_before, today=ON - timedelta(days=1))
    assert raised.value.details == {"reason": "not_today"}
    with pytest.raises(WrongTime):
        day_after = DURING + timedelta(days=1)
        transition(a, s, seen=S.BOOKED, to=S.ARRIVED, now=day_after, today=ON + timedelta(days=1))


def test_d19_an_overnight_session_can_move_after_midnight_while_it_runs() -> None:
    late = datetime(2026, 10, 19, 17, 30, tzinfo=UTC)  # 23:00 Kolkata, until 02:00
    s = session(starts=late)
    after_midnight = late + timedelta(hours=2)
    assert is_session_day(s, now=after_midnight, today=ON + timedelta(days=1))
    assert not is_session_day(s, now=late + timedelta(hours=4), today=ON + timedelta(days=1))


def test_d19_no_show_waits_for_the_session_or_the_slot_to_start() -> None:
    tokens = session()
    a = booked(tokens)
    with pytest.raises(WrongTime) as raised:
        move(a, tokens, S.BOOKED, S.NO_SHOW, BEFORE)
    assert raised.value.details == {"reason": "not_started"}
    move(a, tokens, S.BOOKED, S.NO_SHOW, STARTS)
    move(a, tokens, S.NO_SHOW, S.ARRIVED, DURING)  # late arrival the same day
    assert a.status is S.ARRIVED

    slots = session(BookingMode.SLOTS)
    b = booked(slots, STARTS + timedelta(hours=1))
    with pytest.raises(WrongTime):
        move(b, slots, S.BOOKED, S.NO_SHOW, DURING)  # session started, the slot not yet
    move(b, slots, S.BOOKED, S.NO_SHOW, STARTS + timedelta(hours=1))


def test_r11_a_walk_in_takes_the_earliest_free_slot_that_has_not_ended() -> None:
    s = session(BookingMode.SLOTS)
    second, third = STARTS + timedelta(hours=1), STARTS + timedelta(hours=2)
    assert first_free_slot(s, taken=[], now=BEFORE) == STARTS
    assert first_free_slot(s, taken=[STARTS], now=BEFORE) == second
    assert first_free_slot(s, taken=[], now=second + timedelta(minutes=5)) == second
    assert first_free_slot(s, taken=[second], now=second) == third
    assert first_free_slot(s, taken=[third], now=third) is None
    assert first_free_slot(session(), taken=[], now=BEFORE) is None  # token mode has no slots


def test_wait_minutes_runs_from_arrival_to_now_or_to_the_start() -> None:
    s = session()
    a = booked(s)
    assert wait_minutes(a, DURING) is None
    move(a, s, S.BOOKED, S.ARRIVED, STARTS)
    assert wait_minutes(a, DURING) == 20
    move(a, s, S.ARRIVED, S.IN_CONSULTATION, STARTS + timedelta(minutes=7))
    assert wait_minutes(a, ENDS) == 7
    a.status = S.NO_SHOW
    assert wait_minutes(a, ENDS) is None
