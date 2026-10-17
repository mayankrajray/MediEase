"""Booking rules (FR-APT-04, FR-APT-05; spec R3-R8, AC1, AC2; decisions D10-D15). Pure."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mediease_api.domain.appointments.appointment import Appointment, history_entry
from mediease_api.domain.appointments.errors import (
    AlreadyBooked,
    InPast,
    NotModifiable,
    OutsideSchedule,
    SessionClosed,
    SessionFull,
    SlotTaken,
)
from mediease_api.domain.appointments.status import (
    ACTIVE_STATUSES,
    STAFF_CANCEL_REASONS,
    STAFF_SOURCES,
    AppointmentSource,
    AppointmentStatus,
    CancelReason,
)
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import (
    PlannedSession,
    Session,
    SessionStatus,
    reconcile,
)
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import new_id

CLINIC = new_id()
DOCTOR = new_id()
ON = date(2026, 10, 19)
STARTS = datetime(2026, 10, 19, 4, 30, tzinfo=UTC)  # 10:00 in Asia/Kolkata
ENDS = STARTS + timedelta(hours=3)
BEFORE = STARTS - timedelta(days=1)


def plan(
    mode: BookingMode = BookingMode.TOKENS,
    *,
    capacity: int = 3,
    slot: int | None = None,
    starts: datetime = STARTS,
    ends: datetime = ENDS,
) -> PlannedSession:
    if mode is BookingMode.SLOTS:
        slot = slot or 60
        capacity = int((ends - starts) / timedelta(minutes=slot))
    return PlannedSession(DOCTOR, ON, starts, ends, mode, slot, capacity)


def session(mode: BookingMode = BookingMode.TOKENS, **kw: object) -> Session:
    return Session.from_plan(plan(mode, **kw), id=new_id(), clinic_id=CLINIC, now=BEFORE)  # type: ignore[arg-type]


def book(s: Session, active: list[Appointment], **kw: object) -> Appointment:
    appointment = Appointment.book(
        s,
        id=new_id(),
        patient_id=kw.pop("patient_id", new_id()),  # type: ignore[arg-type]
        active=active,
        now=kw.pop("now", BEFORE),  # type: ignore[arg-type]
        **kw,  # type: ignore[arg-type]
    )
    active.append(appointment)
    return appointment


# --- Token mode (R4, AC2) ------------------------------------------------------------------------


def test_ac2_tokens_are_never_reused_after_a_cancellation() -> None:
    s = session(capacity=5)
    active: list[Appointment] = []
    first, second, third = (book(s, active) for _ in range(3))
    assert [a.token_number for a in (first, second, third)] == [1, 2, 3]
    assert all(a.slot_start is None for a in active)

    second.cancel(s, reason=CancelReason.PATIENT_REQUEST, now=BEFORE)

    assert s.booked_count == 2 and s.next_token == 4
    assert book(s, active).token_number == 4


def test_r5_a_full_token_session_is_refused_and_cancel_frees_a_place() -> None:
    s = session(capacity=1)
    active: list[Appointment] = []
    only = book(s, active)
    with pytest.raises(SessionFull):
        book(s, active)
    only.cancel(s, reason=CancelReason.DUPLICATE, now=BEFORE)
    assert book(s, active).token_number == 2


def test_token_mode_refuses_a_slot_start() -> None:
    with pytest.raises(InvalidValue) as raised:
        book(session(), [], slot_start=STARTS)
    assert raised.value.field == "slot_start"


def test_d12_tokens_are_given_out_until_the_session_ends() -> None:
    s = session()
    assert book(s, [], now=ENDS - timedelta(minutes=1)).token_number == 1
    with pytest.raises(InPast):
        book(s, [], now=ENDS)


# --- Slot mode (R3) ------------------------------------------------------------------------------


def test_r3_one_active_appointment_per_slot() -> None:
    s = session(BookingMode.SLOTS, slot=60)
    active: list[Appointment] = []
    first = book(s, active, slot_start=STARTS)
    assert first.token_number is None and first.slot_start == STARTS
    with pytest.raises(SlotTaken):
        book(s, active, slot_start=STARTS)

    first.cancel(s, reason=CancelReason.CLINIC_REQUEST, now=BEFORE)
    assert book(s, active, slot_start=STARTS).slot_start == STARTS


def test_r6_a_slot_off_the_grid_is_outside_the_schedule_and_one_is_required() -> None:
    s = session(BookingMode.SLOTS, slot=60)
    with pytest.raises(OutsideSchedule):
        book(s, [], slot_start=STARTS + timedelta(minutes=30))
    with pytest.raises(OutsideSchedule):
        book(s, [], slot_start=ENDS)
    with pytest.raises(InvalidValue):
        book(s, [])


def test_d12_a_slot_is_bookable_until_it_ends() -> None:
    s = session(BookingMode.SLOTS, slot=60)
    during_first = STARTS + timedelta(minutes=59)
    assert book(s, [], slot_start=STARTS, now=during_first).slot_start == STARTS
    with pytest.raises(InPast):
        book(s, [], slot_start=STARTS, now=STARTS + timedelta(hours=1))


def test_r5_a_slot_session_with_every_slot_taken_is_full() -> None:
    s = session(BookingMode.SLOTS, slot=60)
    active: list[Appointment] = []
    for hour in range(3):
        book(s, active, slot_start=STARTS + timedelta(hours=hour))
    assert s.available == 0
    with pytest.raises(SlotTaken):
        book(s, active, slot_start=STARTS)


# --- Who and where -------------------------------------------------------------------------------


def test_d13_the_same_patient_once_per_session() -> None:
    s = session()
    active: list[Appointment] = []
    patient = new_id()
    first = book(s, active, patient_id=patient)
    with pytest.raises(AlreadyBooked) as raised:
        book(s, active, patient_id=patient)
    assert raised.value.details == {"appointment_id": str(first.id)}

    first.cancel(s, reason=CancelReason.PATIENT_REQUEST, now=BEFORE)
    assert book(s, active, patient_id=patient).token_number == 2


def test_d10_a_closed_or_retired_session_takes_no_bookings() -> None:
    s = session()
    s.close(BEFORE)
    with pytest.raises(SessionClosed):
        book(s, [])
    s.status = SessionStatus.CANCELLED
    with pytest.raises(SessionClosed):
        book(s, [])


def test_the_booking_records_source_reason_and_who() -> None:
    staff = new_id()
    a = book(session(), [], source=AppointmentSource.PHONE, reason="  follow-up ", created_by=staff)
    assert (a.source, a.reason, a.created_by, a.status) == (
        AppointmentSource.PHONE,
        "follow-up",
        staff,
        AppointmentStatus.BOOKED,
    )
    assert book(session(), [], reason="   ").reason is None
    with pytest.raises(InvalidValue):
        book(session(), [], reason="x" * 121)


# --- Cancel (R7, D14) ----------------------------------------------------------------------------


def test_d14_other_needs_a_note_and_notes_are_bounded() -> None:
    s = session()
    a = book(s, [])
    with pytest.raises(InvalidValue):
        a.cancel(s, reason=CancelReason.OTHER, now=BEFORE)
    with pytest.raises(InvalidValue):
        a.cancel(s, reason=CancelReason.OTHER, note="x" * 201, now=BEFORE)
    a.cancel(s, reason=CancelReason.OTHER, note="moved city", now=BEFORE)
    assert (a.status, a.cancel_reason, a.cancel_note, a.cancelled_at) == (
        AppointmentStatus.CANCELLED,
        CancelReason.OTHER,
        "moved city",
        BEFORE,
    )


@pytest.mark.parametrize(
    "status", [AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW]
)
def test_d14_only_booked_or_arrived_appointments_can_be_cancelled(
    status: AppointmentStatus,
) -> None:
    s = session()
    a = book(s, [])
    a.status = status
    with pytest.raises(NotModifiable) as raised:
        a.cancel(s, reason=CancelReason.PATIENT_REQUEST, now=BEFORE)
    assert raised.value.details == {"status": status.value, "action": "cancelled"}


def test_d14_arrived_can_be_cancelled_but_not_after_the_session_ended() -> None:
    s = session()
    a = book(s, [])
    a.status = AppointmentStatus.ARRIVED
    with pytest.raises(NotModifiable):
        a.cancel(s, reason=CancelReason.PATIENT_REQUEST, now=ENDS)
    a.cancel(s, reason=CancelReason.PATIENT_REQUEST, now=ENDS - timedelta(seconds=1))
    assert s.booked_count == 0


def test_d15_only_a_booked_appointment_is_rescheduled() -> None:
    s = session()
    a = book(s, [])
    a.status = AppointmentStatus.ARRIVED
    with pytest.raises(NotModifiable) as raised:
        a.cancel(s, reason=CancelReason.RESCHEDULED, now=BEFORE)
    assert raised.value.details["action"] == "rescheduled"


def test_same_place_means_the_same_token_session_or_the_same_slot() -> None:
    tokens = session()
    a = book(tokens, [])
    assert a.is_same_place(tokens, None)
    assert not a.is_same_place(session(), None)
    slots = session(BookingMode.SLOTS, slot=60)
    b = book(slots, [], slot_start=STARTS)
    assert b.is_same_place(slots, STARTS)
    assert not b.is_same_place(slots, STARTS + timedelta(hours=1))


def test_history_entry_records_the_change_into_the_current_status() -> None:
    a = book(session(), [])
    entry = history_entry(
        a, id=new_id(), from_status=None, changed_by=a.created_by, request_id="req-1"
    )
    assert (entry.from_status, entry.to_status, entry.changed_at, entry.request_id) == (
        None,
        AppointmentStatus.BOOKED,
        a.updated_at,
        "req-1",
    )


def test_staff_choices_exclude_walk_ins_public_bookings_and_rescheduled() -> None:
    assert AppointmentSource.WALK_IN not in STAFF_SOURCES
    assert AppointmentSource.PUBLIC_PAGE not in STAFF_SOURCES
    assert CancelReason.RESCHEDULED not in STAFF_CANCEL_REASONS
    assert AppointmentStatus.CANCELLED not in ACTIVE_STATUSES


# --- Reconciliation with bookings (D10, D11) -----------------------------------------------------


def booked(s: Session, count: int) -> Session:
    s.booked_count = count
    return s


def test_d10_a_booked_session_that_no_longer_matches_is_closed_and_kept() -> None:
    s = booked(session(), 2)
    outcome = reconcile([s], [])
    assert outcome.to_close == (s,) and outcome.kept == (s,) and outcome.to_delete == ()

    s.close(BEFORE)
    again = reconcile([s], [])
    assert again.to_close == () and again.kept == (s,)


def test_d10_a_closed_session_planned_again_reopens() -> None:
    s = booked(session(), 1)
    s.close(BEFORE)
    outcome = reconcile([s], [plan()])
    assert outcome.to_reopen == (s,) and outcome.kept == ()
    s.reopen(BEFORE)
    assert s.is_open


def test_d11_a_capacity_only_change_resizes_a_booked_session() -> None:
    s = booked(session(capacity=3), 2)
    outcome = reconcile([s], [plan(capacity=5)])
    assert outcome.to_resize == ((s, 5),) and outcome.kept == ()

    s.close(BEFORE)
    s.resize(5, BEFORE)
    assert (s.capacity, s.status) == (5, SessionStatus.OPEN)


def test_d11_a_capacity_below_the_bookings_closes_instead() -> None:
    s = booked(session(capacity=3), 3)
    outcome = reconcile([s], [plan(capacity=2)])
    assert outcome.to_resize == () and outcome.to_close == (s,)


def test_d11_any_other_change_closes_a_booked_session() -> None:
    s = booked(session(capacity=3), 1)
    later_end = plan(capacity=5, ends=ENDS + timedelta(hours=1))
    assert reconcile([s], [later_end]).to_close == (s,)
    assert reconcile([s], [plan(BookingMode.SLOTS)]).to_close == (s,)


def test_an_unbooked_closed_session_that_no_longer_matches_is_deleted() -> None:
    s = session()
    s.close(BEFORE)
    assert reconcile([s], []).to_delete == (s,)


def test_retire_keeps_an_unbooked_session_out_of_play() -> None:
    s = session()
    s.retire(BEFORE)
    assert s.status is SessionStatus.CANCELLED and not s.is_open


def test_a_retired_session_is_ignored_by_reconcile_and_revived_by_the_plan() -> None:
    s = session(capacity=3)
    s.next_token = 4
    s.retire(BEFORE)
    assert reconcile([s], []).to_delete == ()

    s.revive(plan(capacity=6), BEFORE)
    assert (s.status, s.capacity, s.next_token) == (SessionStatus.OPEN, 6, 4)
