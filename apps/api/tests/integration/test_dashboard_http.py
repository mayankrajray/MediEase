"""*Today* over HTTP on PostgreSQL (M6-P1; decisions 5A and 6A).

Each role's shape, counts that match the queue, the 7-day strip, the follow-up count matching
its list, the ETag, and clinic B's day never showing in clinic A's.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.messaging.message import Channel, Message, SourceType
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession, Session
from tests.builders import a_doctor, new_id
from tests.conftest import UowFactory, World
from tests.integration.test_appointments_http import _patient
from tests.integration.test_queue_http import _book, _move, _send
from tests.sessions_now import running_session

KOLKATA = ZoneInfo("Asia/Kolkata")
URL = "/api/v1/dashboard/today"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _today(client: FlaskClient) -> dict[str, Any]:
    resp = client.get(URL)
    assert resp.status_code == 200, resp.get_json()
    body: dict[str, Any] = resp.get_json()
    return body


def _local_today() -> Any:
    return datetime.now(KOLKATA).date()


def _past_day(
    uow_factory: UowFactory, db: Engine, world: World, days_ago: int, statuses: list[str]
) -> None:
    """A session ``days_ago`` for clinic A's doctor with one appointment per status."""
    starts = datetime.now(KOLKATA).replace(hour=10, minute=0, second=0, microsecond=0)
    starts = (starts - timedelta(days=days_ago)).astimezone(UTC)
    clinic_id, doctor_id = world.a.clinic.id, world.a.doctor.id
    plan = PlannedSession(
        doctor_id,
        starts.astimezone(KOLKATA).date(),
        starts,
        starts + timedelta(hours=3),
        BookingMode.TOKENS,
        None,
        10,
    )
    desk = world.client_for(world.a.desk)
    patients = [_patient(desk, f"Past Patient{i}") for i in range(len(statuses))]
    ids: list[UUID] = []
    with uow_factory() as uow:
        staff = uow.tenant(clinic_id)
        session = Session.from_plan(plan, id=new_id(), clinic_id=clinic_id, now=starts)
        staff.sessions.add_missing([session])
        active: list[Appointment] = []
        for patient_id in patients:
            appointment = Appointment.book(
                session, id=new_id(), patient_id=UUID(patient_id), active=active, now=starts
            )
            active.append(appointment)
            staff.appointments.add(appointment)
            ids.append(appointment.id)
        staff.sessions.update(session)
        uow.commit()
    # History data: the statuses are set directly, as the day would have left them.
    with db.begin() as conn:
        for appointment_id, status in zip(ids, statuses, strict=True):
            conn.execute(
                text("UPDATE appointments SET status = :s WHERE id = :id"),
                {"s": status, "id": appointment_id},
            )


def _message(uow_factory: UowFactory, world: World, patient_id: str, *, failed: bool) -> None:
    """A message to clinic A's patient today: accepted by the provider, or failed."""
    now = datetime.now(UTC)
    message = Message.prepare(
        id=new_id(),
        clinic_id=world.a.clinic.id,
        patient_id=UUID(patient_id),
        source_type=SourceType.APPOINTMENT,
        source_id=new_id(),
        channel=Channel.CONSOLE,
        provider="console",
        template_key="booking_confirmed",
        template_version=1,
        language=Language.EN,
        variables={"clinic_name": "Sample Clinic"},
        to_phone_encrypted="ciphertext",
        idempotency_key=f"test:{new_id()}",
        request_id=None,
        job_id=None,
        now=now,
    )
    if failed:
        message.fail("WA_TEST_FAILURE", now)
    else:
        message.accepted(provider_message_id=f"console-{new_id()}", now=now)
    with uow_factory() as uow:
        uow.tenant(world.a.clinic.id).messages.add(message)
        uow.commit()


# --- Front desk (scope CLINIC) ------------------------------------------------------------------


def test_m6_p1_front_desk_today_counts_match_the_queue(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    session = running_session(owner, world.a.doctor.id)
    names = ["Asha Rao", "Bina Shah", "Chetan Iyer", "Deepa Nair", "Esha Pai"]
    asha, bina, chetan, deepa, esha = (_book(desk, session["id"], _patient(desk, n)) for n in names)
    assert _move(desk, asha, "BOOKED", "ARRIVED").status_code == 200
    assert _move(desk, bina, "BOOKED", "ARRIVED").status_code == 200
    assert _move(doctor, bina, "ARRIVED", "IN_CONSULTATION").status_code == 200
    assert _move(doctor, bina, "IN_CONSULTATION", "COMPLETED").status_code == 200
    assert _move(desk, chetan, "BOOKED", "NO_SHOW").status_code == 200
    cancelled = _send(desk, "POST", f"/api/v1/appointments/{esha}/cancel", {"reason": "DUPLICATE"})
    assert cancelled.status_code == 200

    resp = desk.get(URL)
    assert resp.status_code == 200, resp.get_json()
    assert resp.headers["Cache-Control"] == "no-store" and resp.headers["ETag"]
    body = resp.get_json()
    assert (body["on_date"], body["scope"], body["doctor_id"]) == (
        _local_today().isoformat(),
        "CLINIC",
        None,
    )
    expected = {
        "total": 4,
        "not_arrived": 1,
        "waiting": 1,
        "in_consultation": 0,
        "completed": 1,
        "no_show": 1,
    }
    assert body["counts"] == expected
    [today] = body["sessions"]
    assert (today["id"], today["doctor_name"], today["counts"]) == (
        session["id"],
        "Dr. Alpha Sample",
        expected,
    )
    # Waiting first, then not yet arrived; code and first name only.
    assert [
        (n["appointment_id"], n["status"], n["patient_first_name"]) for n in body["next_patients"]
    ] == [
        (asha, "ARRIVED", "Asha"),
        (deepa, "BOOKED", "Deepa"),
    ]
    assert all(n["patient_code"] for n in body["next_patients"])
    assert "Rao" not in resp.text and "Nair" not in resp.text
    assert (body["follow_ups_pending"], body["messages_failed"], body["week"]) == (0, 0, None)

    # The same day as the queue shows it.
    queue = desk.get("/api/v1/queue").get_json()
    statuses = Counter(a["status"] for s in queue["sessions"] for a in s["appointments"])
    assert (
        statuses["ARRIVED"],
        statuses["COMPLETED"],
        statuses["NO_SHOW"],
        statuses["BOOKED"],
    ) == (
        expected["waiting"],
        expected["completed"],
        expected["no_show"],
        expected["not_arrived"],
    )


def test_m6_p1_a_quiet_day_is_all_zeros(world: World) -> None:
    body = _today(world.client_for(world.a.desk))
    assert body["counts"]["total"] == 0
    assert (body["sessions"], body["next_patients"]) == ([], [])


# --- Doctor (scope DOCTOR) and owner (the 7-day strip) ------------------------------------------


def test_m6_p1_a_doctor_sees_only_their_own_day(world: World, uow_factory: UowFactory) -> None:
    other = a_doctor(world.a.clinic.id, display_name="Dr. Other Sample")
    with uow_factory() as uow:
        uow.tenant(world.a.clinic.id).doctors.add(other)
        uow.commit()
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    mine = running_session(owner, world.a.doctor.id)
    theirs = running_session(owner, other.id)
    _book(desk, mine["id"], _patient(desk, "Asha Rao"))
    _book(desk, theirs["id"], _patient(desk, "Bina Shah"))
    _book(desk, theirs["id"], _patient(desk, "Chetan Iyer"))

    doctor = _today(world.client_for(world.a.doctor_user))
    assert (doctor["scope"], doctor["doctor_id"]) == ("DOCTOR", str(world.a.doctor.id))
    assert [s["id"] for s in doctor["sessions"]] == [mine["id"]]
    assert doctor["counts"]["total"] == 1
    assert [n["patient_first_name"] for n in doctor["next_patients"]] == ["Asha"]
    assert doctor["messages_failed"] is None
    # Doctors hold USAGE_METRICS_VIEW: their own week, without the clinic's messages.
    assert len(doctor["week"]) == 7
    assert doctor["week"][-1] == {
        "on_date": _local_today().isoformat(),
        "appointments": 1,
        "completed": 0,
        "no_show": 0,
        "messages_sent": None,
    }

    clinic = _today(owner)
    assert (clinic["scope"], clinic["counts"]["total"]) == ("CLINIC", 3)
    assert {s["id"] for s in clinic["sessions"]} == {mine["id"], theirs["id"]}
    assert clinic["week"][-1]["appointments"] == 3 and clinic["week"][-1]["messages_sent"] == 0

    front = _today(desk)
    assert (front["scope"], front["week"]) == ("CLINIC", None)  # no owner strip


def test_m6_p1_the_owner_strip_counts_past_days_and_messages(
    world: World, uow_factory: UowFactory, db: Engine
) -> None:
    _past_day(uow_factory, db, world, 2, ["COMPLETED", "COMPLETED", "NO_SHOW"])
    _past_day(uow_factory, db, world, 9, ["COMPLETED"])  # outside the 7 days
    desk = world.client_for(world.a.desk)
    patient = _patient(desk, "Farah Khan")
    _message(uow_factory, world, patient, failed=False)
    _message(uow_factory, world, patient, failed=True)

    body = _today(world.client_for(world.a.owner))
    week = body["week"]
    first = _local_today() - timedelta(days=6)
    assert [d["on_date"] for d in week] == [
        (first + timedelta(days=i)).isoformat() for i in range(7)
    ]
    assert week[-3] == {
        "on_date": (_local_today() - timedelta(days=2)).isoformat(),
        "appointments": 3,
        "completed": 2,
        "no_show": 1,
        "messages_sent": 0,
    }
    assert sum(d["appointments"] for d in week) == 3
    assert week[-1]["messages_sent"] == 1
    assert body["messages_failed"] == 1


def test_m6_p1_pending_follow_ups_is_the_length_of_the_list(
    world: World, uow_factory: UowFactory
) -> None:
    from tests.integration.test_reminders_http import _past_prescription

    desk = world.client_for(world.a.desk)
    # _past_visit makes a session per day for the clinic's doctor: one day each.
    for days_ago, name in ((30, "Asha Rao"), (31, "Bina Shah")):
        _past_prescription(
            uow_factory, world, _patient(desk, name), days_ago=days_ago, follow_up_after=7
        )

    listed = desk.get("/api/v1/follow-ups/pending").get_json()["items"]
    assert len(listed) == 2
    assert _today(desk)["follow_ups_pending"] == 2


# --- ETag, access and tenancy -------------------------------------------------------------------


def test_m6_p1_r12_an_unchanged_day_is_a_304_and_a_change_is_not(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    first = desk.get(URL)
    tag = first.headers["ETag"]
    again = desk.get(URL, headers={"If-None-Match": tag})
    assert (again.status_code, again.headers["ETag"], again.data) == (304, tag, b"")
    _book(desk, session["id"], _patient(desk))
    changed = desk.get(URL, headers={"If-None-Match": tag})
    assert changed.status_code == 200 and changed.headers["ETag"] != tag


def test_m6_p1_today_needs_a_clinic_member(world: World) -> None:
    assert world.anonymous().get(URL).status_code == 401
    assert world.client_for(world.ops).get(URL).status_code == 403


def test_nfr_08_m6_p1_another_clinics_day_never_appears(world: World) -> None:
    owner_b = world.client_for(world.b.owner)
    session_b = running_session(owner_b, world.b.doctor.id)
    _book(owner_b, session_b["id"], _patient(owner_b, "Bina Shah"))

    a = _today(world.client_for(world.a.owner))
    assert (a["counts"]["total"], a["sessions"], a["next_patients"]) == (0, [], [])
    assert a["week"][-1]["appointments"] == 0
    b = _today(owner_b)
    assert (b["counts"]["total"], b["sessions"][0]["id"]) == (1, session_b["id"])
