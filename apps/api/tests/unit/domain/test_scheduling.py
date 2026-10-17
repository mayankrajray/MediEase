"""Scheduling rules (FR-APT-01, FR-APT-02; spec R1-R4, R14-R18; AC5). Pure: no clock, no I/O."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from mediease_api.domain.clinics.clinic import Clinic
from mediease_api.domain.scheduling.blocks import (
    BlockShape,
    WeekInterval,
    WeeklyBlock,
    block_minutes,
    check_no_overlap,
)
from mediease_api.domain.scheduling.errors import (
    InvalidBlock,
    LeaveExists,
    ModeIncompatible,
    ScheduleOverlap,
)
from mediease_api.domain.scheduling.exceptions import (
    ExceptionKind,
    ScheduleException,
    check_editable_date,
)
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import (
    PlannedSession,
    Session,
    horizon,
    overlaps,
    plan_day,
    reconcile,
    session_bounds,
)
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import LATER, NOW, a_clinic, new_id

KOLKATA = "Asia/Kolkata"
MONDAY = date(2026, 10, 19)
TUESDAY = date(2026, 10, 20)
SUNDAY = date(2026, 10, 25)
CLINIC = new_id()
DOCTOR = new_id()

SLOTS, TOKENS = BookingMode.SLOTS, BookingMode.TOKENS


def shape(start: str, end: str, slot: int | None = 15, capacity: int | None = 12) -> BlockShape:
    return BlockShape(time.fromisoformat(start), time.fromisoformat(end), slot, capacity)


def block(weekday: int, start: str, end: str, **kw: object) -> WeeklyBlock:
    valid_from = kw.pop("valid_from", date(2026, 10, 1))
    mode = kw.pop("mode", TOKENS)
    return WeeklyBlock.create(
        id=new_id(),
        clinic_id=CLINIC,
        doctor_id=DOCTOR,
        weekday=weekday,
        shape=shape(start, end, **kw),  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        valid_from=valid_from,  # type: ignore[arg-type]
        now=NOW,
    )


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


# --- Block length and validation (R14, D2) ----------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "minutes"),
    [
        ("10:00", "13:00", 180),
        ("23:00", "01:00", 120),
        ("22:00", "10:00", 720),
        ("00:00", "00:15", 15),
    ],
)
def test_r14_d2_an_end_at_or_before_the_start_is_the_next_day(
    start: str, end: str, minutes: int
) -> None:
    assert block_minutes(time.fromisoformat(start), time.fromisoformat(end)) == minutes


def test_r14_a_daytime_inversion_is_refused_as_too_long_but_a_night_shift_passes() -> None:
    # The developer's refinement: 13:00-10:00 would be 21 hours, so it cannot pass as overnight.
    with pytest.raises(InvalidBlock) as excinfo:
        shape("13:00", "10:00").validate(TOKENS)
    assert excinfo.value.code == "SCH_INVALID_BLOCK"
    assert "12 hours" in excinfo.value.reason
    assert shape("23:00", "01:00").validate(TOKENS).overnight is True
    assert (
        shape("20:00", "08:00", slot=60).validate(SLOTS).minutes == 720
    )  # exactly 12 h is allowed


@pytest.mark.parametrize(
    ("bad", "mode", "reason"),
    [
        (shape("10:00", "10:10"), TOKENS, "at least 15 minutes"),
        (shape("10:00", "10:00"), TOKENS, "at most 12 hours"),  # equal times = 24 h
        (shape("10:00", "11:00", slot=25), SLOTS, "divide"),
        (shape("10:00", "11:00", slot=3), SLOTS, "5 to 120"),
        (shape("10:00", "11:00", capacity=0), TOKENS, "1 to 500"),
        (shape("10:00", "11:00", slot=None), SLOTS, "needs a slot length"),
        (shape("10:00", "11:00", capacity=None), TOKENS, "needs a capacity"),
    ],
)
def test_r14_blocks_that_cannot_be_scheduled_name_the_reason(
    bad: BlockShape, mode: BookingMode, reason: str
) -> None:
    with pytest.raises(InvalidBlock) as excinfo:
        bad.validate(mode, index=2)
    assert reason in excinfo.value.reason
    assert excinfo.value.details["index"] == "2"


def test_times_must_be_whole_minutes_and_weekdays_0_to_6() -> None:
    with pytest.raises(InvalidValue):
        BlockShape(time(10, 0, 30), time(11), None, 5).validate(TOKENS)
    with pytest.raises(InvalidValue):
        block(7, "10:00", "11:00")


def test_d3_slot_capacity_is_derived_and_token_capacity_is_stated() -> None:
    s = shape("10:00", "13:00", slot=15, capacity=40)
    assert s.capacity_for(SLOTS) == 12
    assert s.capacity_for(TOKENS) == 40
    with pytest.raises(ModeIncompatible):
        shape("10:00", "13:00", slot=None).capacity_for(SLOTS)
    with pytest.raises(ModeIncompatible):
        shape("10:00", "13:00", capacity=None).capacity_for(TOKENS)
    assert shape("10:00", "11:00", capacity=None).supports(SLOTS)
    assert not shape("10:00", "11:00", capacity=None).supports(TOKENS)


# --- Overlap on the circle of the week (R15, D7) ------------------------------------------------


def test_r15_overlap_within_a_day_is_refused_and_touching_blocks_are_fine() -> None:
    check_no_overlap([block(0, "09:00", "13:00").interval, block(0, "13:00", "17:00").interval])
    with pytest.raises(ScheduleOverlap) as excinfo:
        check_no_overlap([block(0, "09:00", "13:00").interval, block(0, "12:00", "14:00").interval])
    assert excinfo.value.details == {"first": "0", "second": "1"}


def test_r15_an_overnight_block_collides_with_the_next_mornings_block() -> None:
    with pytest.raises(ScheduleOverlap):
        check_no_overlap([block(1, "22:00", "02:00").interval, block(2, "01:00", "05:00").interval])
    check_no_overlap([block(1, "22:00", "02:00").interval, block(2, "02:00", "05:00").interval])


def test_r15_sunday_night_spills_into_monday_morning() -> None:
    with pytest.raises(ScheduleOverlap):
        check_no_overlap([block(6, "22:00", "02:00").interval, block(0, "01:00", "05:00").interval])
    assert WeekInterval(10079, 2).overlaps(WeekInterval(0, 1))


def test_blocks_on_different_days_do_not_overlap() -> None:
    check_no_overlap([block(day, "10:00", "13:00").interval for day in range(7)])


# --- Planning (R1, R2, AC5) --------------------------------------------------------------------


def test_r1_r3_a_slot_block_plans_one_session_with_its_slots_in_utc() -> None:
    planned = plan_day(
        doctor_id=DOCTOR,
        on_date=MONDAY,
        timezone=KOLKATA,
        mode=SLOTS,
        blocks=[block(0, "10:00", "13:00", mode=SLOTS)],
        exceptions=[],
    )
    assert [(p.starts_at, p.ends_at, p.capacity, p.slot_minutes) for p in planned] == [
        (utc("2026-10-19T04:30:00"), utc("2026-10-19T07:30:00"), 12, 15)
    ]
    session = Session.from_plan(planned[0], id=new_id(), clinic_id=CLINIC, now=NOW)
    slots = session.slots()
    assert len(slots) == 12
    assert slots[0] == (utc("2026-10-19T04:30:00"), utc("2026-10-19T04:45:00"))
    assert slots[-1][1] == session.ends_at
    assert session.available == 12


def test_ac5_r2_a_23_to_01_session_belongs_to_its_start_date_with_correct_utc() -> None:
    planned = plan_day(
        doctor_id=DOCTOR,
        on_date=MONDAY,
        timezone=KOLKATA,
        mode=SLOTS,
        blocks=[block(0, "23:00", "01:00", slot=30, mode=SLOTS)],
        exceptions=[],
    )
    assert len(planned) == 1
    assert planned[0].on_date == MONDAY
    assert planned[0].starts_at == utc("2026-10-19T17:30:00")
    assert planned[0].ends_at == utc("2026-10-19T19:30:00")  # 01:00 IST on Tuesday
    session = Session.from_plan(planned[0], id=new_id(), clinic_id=CLINIC, now=NOW)
    assert [s for s, _ in session.slots()] == [
        utc("2026-10-19T17:30:00"),
        utc("2026-10-19T18:00:00"),
        utc("2026-10-19T18:30:00"),
        utc("2026-10-19T19:00:00"),
    ]
    # Tuesday plans nothing from Monday's block, even though it ends on Tuesday.
    assert (
        plan_day(
            doctor_id=DOCTOR,
            on_date=TUESDAY,
            timezone=KOLKATA,
            mode=SLOTS,
            blocks=[block(0, "23:00", "01:00", slot=30, mode=SLOTS)],
            exceptions=[],
        )
        == []
    )


def test_r2_kolkata_midnight_on_both_edges() -> None:
    early = session_bounds(MONDAY, shape("00:00", "00:30"), KOLKATA)
    late = session_bounds(MONDAY, shape("23:30", "00:00"), KOLKATA)
    assert early == (utc("2026-10-18T18:30:00"), utc("2026-10-18T19:00:00"))  # still Sunday in UTC
    assert late == (utc("2026-10-19T18:00:00"), utc("2026-10-19T18:30:00"))


def test_r1_only_blocks_valid_on_the_date_and_on_its_weekday_are_planned() -> None:
    old = block(0, "09:00", "12:00", valid_from=date(2026, 9, 1))
    old.close(last_day=date(2026, 10, 18), now=LATER)
    new = block(0, "14:00", "17:00", valid_from=MONDAY)
    tuesday = block(1, "10:00", "11:00")
    planned = plan_day(
        doctor_id=DOCTOR,
        on_date=MONDAY,
        timezone=KOLKATA,
        mode=TOKENS,
        blocks=[old, new, tuesday],
        exceptions=[],
    )
    assert [p.starts_at for p in planned] == [utc("2026-10-19T08:30:00")]
    assert old.valid_on(date(2026, 10, 18)) and not old.valid_on(MONDAY)
    with pytest.raises(InvalidValue):
        new.close(last_day=date(2026, 10, 1), now=LATER)


def test_r17_leave_removes_the_days_blocks_and_r18_extras_are_added() -> None:
    leave = ScheduleException.leave(
        id=new_id(), clinic_id=CLINIC, doctor_id=DOCTOR, on_date=MONDAY, now=NOW
    )
    extra = ScheduleException.extra(
        id=new_id(),
        clinic_id=CLINIC,
        doctor_id=DOCTOR,
        on_date=MONDAY,
        shape=shape("18:00", "19:00", capacity=5),
        mode=TOKENS,
        now=NOW,
        note="  Evening clinic ",
    )
    assert (
        extra.note == "Evening clinic" and leave.kind is ExceptionKind.LEAVE and leave.shape is None
    )
    planned = plan_day(
        doctor_id=DOCTOR,
        on_date=MONDAY,
        timezone=KOLKATA,
        mode=TOKENS,
        blocks=[block(0, "10:00", "13:00")],
        exceptions=[leave, extra],
    )
    assert [(p.starts_at, p.capacity) for p in planned] == [(utc("2026-10-19T12:30:00"), 5)]


def test_another_doctors_rules_and_another_dates_exceptions_do_not_apply() -> None:
    other_doctor_leave = ScheduleException.leave(
        id=new_id(), clinic_id=CLINIC, doctor_id=new_id(), on_date=MONDAY, now=NOW
    )
    tuesday_leave = ScheduleException.leave(
        id=new_id(), clinic_id=CLINIC, doctor_id=DOCTOR, on_date=TUESDAY, now=NOW
    )
    planned = plan_day(
        doctor_id=DOCTOR,
        on_date=MONDAY,
        timezone=KOLKATA,
        mode=TOKENS,
        blocks=[block(0, "10:00", "13:00")],
        exceptions=[other_doctor_leave, tuesday_leave],
    )
    assert len(planned) == 1


def test_r18_exception_dates_are_today_to_the_horizon() -> None:
    today = date(2026, 10, 17)
    assert horizon(today) == date(2027, 4, 15)
    assert check_editable_date(today, today=today, horizon=horizon(today)) == today
    with pytest.raises(InvalidValue):
        check_editable_date(date(2026, 10, 16), today=today, horizon=horizon(today))
    with pytest.raises(InvalidValue):
        check_editable_date(date(2027, 4, 16), today=today, horizon=horizon(today))


# --- Reconciliation (D4) -------------------------------------------------------------------------


def _session(plan: PlannedSession, booked: int = 0) -> Session:
    session = Session.from_plan(plan, id=new_id(), clinic_id=CLINIC, now=NOW)
    session.booked_count = booked
    return session


def _plan(start: str, end: str, mode: BookingMode = TOKENS) -> PlannedSession:
    return plan_day(
        doctor_id=DOCTOR,
        on_date=MONDAY,
        timezone=KOLKATA,
        mode=mode,
        blocks=[block(0, start, end, mode=mode)],
        exceptions=[],
    )[0]


def test_d4_unchanged_sessions_stay_unbooked_changes_go_and_booked_ones_are_kept() -> None:
    same = _session(_plan("10:00", "13:00"))
    moved = _session(_plan("14:00", "17:00"))
    moved_but_booked = _session(_plan("18:00", "20:00"), booked=2)
    new_plan = [_plan("10:00", "13:00"), _plan("15:00", "17:00")]

    outcome = reconcile([same, moved, moved_but_booked], new_plan)

    assert outcome.to_delete == (moved,)
    assert outcome.kept == (moved_but_booked,)


def test_d4_r19_a_mode_change_makes_every_unbooked_session_stale() -> None:
    session = _session(_plan("10:00", "13:00", TOKENS))
    outcome = reconcile([session], [_plan("10:00", "13:00", SLOTS)])
    assert outcome.to_delete == (session,)


def test_overlaps_is_half_open() -> None:
    a = (utc("2026-10-19T04:30:00"), utc("2026-10-19T07:30:00"))
    assert overlaps(a, (utc("2026-10-19T07:00:00"), utc("2026-10-19T08:00:00")))
    assert not overlaps(a, (utc("2026-10-19T07:30:00"), utc("2026-10-19T08:00:00")))


def test_token_sessions_have_no_slots() -> None:
    assert _session(_plan("10:00", "13:00")).slots() == []


# --- Clinic booking mode and errors --------------------------------------------------------------


def test_fr_apt_02_clinics_default_to_tokens_and_can_change_mode() -> None:
    clinic: Clinic = a_clinic()
    assert clinic.booking_mode is TOKENS
    assert clinic.change_booking_mode(SLOTS, now=LATER) is True
    assert clinic.booking_mode is SLOTS and clinic.updated_at == LATER
    assert clinic.change_booking_mode(SLOTS, now=LATER) is False


def test_scheduling_errors_carry_stable_codes() -> None:
    assert LeaveExists().code == "SCH_LEAVE_EXISTS"
    assert ScheduleOverlap().details == {}
    incompatible = ModeIncompatible("SLOTS", "slot length")
    assert incompatible.code == "SCH_MODE_INCOMPATIBLE"
    assert incompatible.details == {"mode": "SLOTS", "needs": "slot length"}
