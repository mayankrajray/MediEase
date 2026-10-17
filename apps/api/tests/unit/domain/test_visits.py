"""Visit rules (FR-VIS-01, 02, 05; spec R1, R3, AC6; M4-P1 decisions 1A-6A). Pure."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.queue import transition
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession, Session
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.visits.errors import (
    VisitLocked,
    VisitNotCompleted,
    VisitNotStartable,
    VisitNotYours,
    VisitStale,
)
from mediease_api.domain.visits.visit import LOCK_AFTER, Visit, VisitStatus
from mediease_api.domain.visits.vitals import Vitals
from tests.builders import new_id

S = AppointmentStatus
ON = date(2026, 10, 19)
STARTS = datetime(2026, 10, 19, 4, 30, tzinfo=UTC)
DURING = STARTS + timedelta(minutes=20)


def appointment(status: S = S.IN_CONSULTATION) -> Appointment:
    plan = PlannedSession(
        new_id(), ON, STARTS, STARTS + timedelta(hours=3), BookingMode.TOKENS, None, 5
    )
    session = Session.from_plan(plan, id=new_id(), clinic_id=new_id(), now=STARTS - timedelta(1))
    a = Appointment.book(
        session, id=new_id(), patient_id=new_id(), active=[], now=STARTS - timedelta(1)
    )
    path = [S.ARRIVED, S.IN_CONSULTATION, S.COMPLETED]
    for to in path[: path.index(status) + 1] if status in path else []:
        transition(a, session, seen=a.status, to=to, now=DURING, today=ON)
    return a


def started(a: Appointment | None = None) -> Visit:
    a = a or appointment()
    return Visit.start(a, id=new_id(), doctor_id=a.doctor_id, created_by=new_id(), now=DURING)


# --- Start (R1, decisions 1A and 5A) -------------------------------------------------------------


def test_fr_vis_01_a_visit_starts_from_an_appointment_in_consultation() -> None:
    a = appointment()
    visit = started(a)
    assert (visit.appointment_id, visit.patient_id, visit.doctor_id, visit.clinic_id) == (
        a.id,
        a.patient_id,
        a.doctor_id,
        a.clinic_id,
    )
    assert (visit.status, visit.revision, visit.started_at, visit.locked_at) == (
        VisitStatus.OPEN,
        1,
        DURING,
        None,
    )
    assert not visit.vitals


@pytest.mark.parametrize("status", [S.BOOKED, S.ARRIVED, S.COMPLETED])
def test_r1_a_visit_does_not_start_outside_the_consultation(status: S) -> None:
    with pytest.raises(VisitNotStartable) as caught:
        started(appointment(status))
    assert caught.value.details == {"status": status.value}


def test_r1_only_the_appointments_doctor_starts_its_visit() -> None:
    with pytest.raises(VisitNotYours):
        Visit.start(appointment(), id=new_id(), doctor_id=new_id(), created_by=new_id(), now=DURING)


# --- Edit (FR-VIS-02, decision 4A) ---------------------------------------------------------------


def test_fr_vis_02_edit_returns_the_changed_field_names_and_bumps_the_revision() -> None:
    visit = started()
    later = DURING + timedelta(minutes=5)
    changed = visit.edit(
        {"chief_complaint": "  fever for two days ", "notes": None, "vitals": Vitals.parse({})},
        seen_revision=1,
        now=later,
    )
    assert changed == ("chief_complaint",)
    assert (visit.chief_complaint, visit.revision, visit.updated_at) == (
        "fever for two days",
        2,
        later,
    )

    assert visit.edit({"chief_complaint": "fever for two days"}, seen_revision=2, now=later) == ()
    assert visit.revision == 2  # nothing changed, no new revision

    vitals = Vitals.parse({"temp_c": 38.4, "pulse": 96})
    assert visit.edit({"vitals": vitals, "diagnosis": " "}, seen_revision=2, now=later) == (
        "vitals",
    )
    assert visit.vitals.as_json() == {"pulse": 96, "temp_c": 38.4}


def test_decision_4a_an_edit_from_an_older_revision_is_stale() -> None:
    visit = started()
    visit.edit({"notes": "first tab"}, seen_revision=1, now=DURING)
    with pytest.raises(VisitStale) as caught:
        visit.edit({"notes": "second tab"}, seen_revision=1, now=DURING)
    assert caught.value.details == {"revision": "2"}
    assert visit.notes == "first tab"


def test_r17_validation_errors_name_the_field_never_the_value() -> None:
    visit = started()
    secret = "SENTINEL-clinical-" + "x" * 600
    with pytest.raises(InvalidValue) as caught:
        visit.edit({"chief_complaint": secret}, seen_revision=1, now=DURING)
    assert caught.value.field == "chief_complaint"
    assert "SENTINEL" not in str(caught.value) and "SENTINEL" not in str(caught.value.details)
    with pytest.raises(InvalidValue):
        visit.edit({"patient_id": "x"}, seen_revision=1, now=DURING)
    with pytest.raises(InvalidValue):
        visit.edit({"notes": 5}, seen_revision=1, now=DURING)
    with pytest.raises(InvalidValue):
        visit.edit({"vitals": {"pulse": 80}}, seen_revision=1, now=DURING)


# --- Complete and the 24-hour lock (R3, AC6, decision 6A) ----------------------------------------


def test_r3_complete_locks_exactly_24_hours_later_and_is_idempotent() -> None:
    visit = started()
    done = DURING + timedelta(minutes=10)
    assert visit.complete(done) is True
    assert (visit.status, visit.completed_at, visit.locked_at, visit.revision) == (
        VisitStatus.COMPLETED,
        done,
        done + LOCK_AFTER,
        2,
    )
    assert visit.complete(done + timedelta(hours=1)) is False
    assert visit.completed_at == done

    just_before = done + LOCK_AFTER - timedelta(seconds=1)
    assert not visit.is_locked(just_before)
    assert visit.edit({"notes": "corrected"}, seen_revision=2, now=just_before) == ("notes",)
    assert visit.is_locked(done + LOCK_AFTER)


def test_ac6_a_visit_completed_25_hours_ago_takes_an_addendum_not_an_edit() -> None:
    visit = started()
    visit.complete(DURING)
    later = DURING + timedelta(hours=25)
    with pytest.raises(VisitLocked) as caught:
        visit.edit({"notes": "late change"}, seen_revision=visit.revision, now=later)
    assert caught.value.details == {"locked_at": (DURING + LOCK_AFTER).isoformat()}
    # Locked wins over stale: the lasting reason, not "reload".
    with pytest.raises(VisitLocked):
        visit.edit({"notes": "late change"}, seen_revision=1, now=later)

    author = new_id()
    note = visit.addendum(id=new_id(), author_user_id=author, body=" lab result seen ", now=later)
    assert (note.visit_id, note.author_user_id, note.body, note.created_at) == (
        visit.id,
        author,
        "lab result seen",
        later,
    )


def test_r3_an_open_visit_is_edited_not_amended_and_addenda_need_text() -> None:
    visit = started()
    with pytest.raises(VisitNotCompleted):
        visit.addendum(id=new_id(), author_user_id=new_id(), body="note", now=DURING)
    visit.complete(DURING)
    with pytest.raises(InvalidValue):
        visit.addendum(id=new_id(), author_user_id=new_id(), body="   ", now=DURING)
    with pytest.raises(InvalidValue):
        visit.addendum(id=new_id(), author_user_id=new_id(), body="x" * 5001, now=DURING)


def test_decision_3a_only_the_visits_doctor_writes() -> None:
    visit = started()
    visit.check_writer(visit.doctor_id)
    for other in (new_id(), None):
        with pytest.raises(VisitNotYours):
            visit.check_writer(other)


def test_the_domain_refuses_a_naive_clock() -> None:
    visit = started()
    with pytest.raises(InvalidValue):
        visit.complete(datetime(2026, 10, 19, 10, 0))
    assert visit.status is VisitStatus.OPEN


# --- Vitals ---------------------------------------------------------------------------------------


def test_vitals_are_a_closed_set_with_input_bounds() -> None:
    vitals = Vitals.parse(
        {"bp_systolic": 120, "bp_diastolic": 80.0, "spo2": 98, "weight_kg": 12.5, "pulse": None}
    )
    assert vitals.as_json() == {
        "bp_diastolic": 80,
        "bp_systolic": 120,
        "spo2": 98,
        "weight_kg": 12.5,
    }
    assert Vitals.parse(vitals.as_json()) == vitals
    for bad in (
        {"glucose": 5},
        {"temp_c": 370},
        {"pulse": 72.5},
        {"spo2": True},
        {"height_cm": "120"},
    ):
        with pytest.raises(InvalidValue) as caught:
            Vitals.parse(bad)
        assert caught.value.field.startswith("vitals.")
