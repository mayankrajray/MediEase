"""The notification service and centre end to end on PostgreSQL (M6a-P7, ADR-0017).

FR-NTF-02 (one service), FR-NTF-03 (in-app centre), FR-NTF-04 (failed messages), FR-NTF-05
(preferences), FR-NTF-06 (idempotent, non-clinical). Changes go through HTTP, so each event is
published by the real use case in its own transaction.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.application.jobs.purge import PurgeExpired
from mediease_api.application.notifications.service import publish
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.messaging.errors import MSG_RECIPIENT_INVALID, ProviderRefused
from mediease_api.domain.notifications.events import (
    AppointmentBooked,
    AppointmentCancelled,
    MessageFailed,
)
from mediease_api.domain.notifications.notification import Notification, NotificationKind
from tests.builders import NOW, new_id
from tests.conftest import UowFactory, World
from tests.fakes import FakeClock, FakeIds
from tests.integration.test_appointments_http import MONDAY, TUESDAY, _patient, _schedule, _session
from tests.integration.test_messaging_db import _booked, _consenting_patient, _job, _raise, _rig
from tests.integration.test_visits_http import _send
from tests.sessions_now import running_session

NOTIFICATIONS = "/api/v1/notifications"
PASSWORD = "a-new-staff-password"  # gitleaks:allow (synthetic test value)
# "First · CODE <verb> for <day> <Mon>, token N" (or a time): typed values only (FR-NTF-06).
BOOKED = re.compile(r"^Asha · \S+ booked for \d{1,2} [A-Z][a-z]{2}, (token \d+|\d\d:\d\d)$")


@pytest.fixture
def db(migrated_database_url: str) -> Any:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _items(client: FlaskClient) -> list[dict[str, Any]]:
    resp = client.get(NOTIFICATIONS)
    assert resp.status_code == 200, resp.get_json()
    assert resp.headers["Cache-Control"] == "no-store"
    return list(resp.get_json()["items"])


def _unread(client: FlaskClient) -> int:
    return int(client.get(f"{NOTIFICATIONS}/summary").get_json()["unread"])


def _count(db: Engine, kind: str) -> int:
    with db.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM notifications WHERE kind = :k"), {"k": kind}
            ).scalar_one()
        )


def _jobs(db: Engine, key: str) -> int:
    with db.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM jobs WHERE dedupe_key = :k"), {"k": key}
            ).scalar_one()
        )


def _book(world: World, desk: FlaskClient, session_id: str, name: str = "Asha Rao") -> str:
    resp = _send(
        desk,
        "POST",
        "/api/v1/appointments",
        {"session_id": session_id, "patient_id": _patient(desk, name)},
    )
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["id"])


# --- Events from the features (FR-NTF-02) -------------------------------------------------------


def test_fr_ntf_02_a_desk_booking_tells_the_doctor_and_queues_the_confirmation(
    world: World, db: Engine
) -> None:
    desk, appointment_id = _booked(world)
    doctor = world.client_for(world.a.doctor_user)

    [item] = _items(doctor)
    assert item["kind"] == "appointment.booked"
    assert BOOKED.match(item["title"]), item["title"]
    assert re.fullmatch(r"/queue\?date=\d{4}-\d{2}-\d{2}", item["link"])
    assert (item["entity_type"], item["entity_id"], item["read_at"]) == (
        "appointment",
        appointment_id,
        None,
    )
    # The WhatsApp channel is the M5 job with its M5 key: nothing else changed for the patient.
    assert _jobs(db, f"booking_confirmed:{appointment_id}") == 1
    # The desk caused it and the owner is not the doctor: neither is told.
    assert _items(desk) == []
    assert _items(world.client_for(world.a.owner)) == []


def test_fr_ntf_06_an_event_published_again_adds_nothing_and_a_rollback_leaves_nothing(
    world: World, db: Engine, uow_factory: UowFactory
) -> None:
    _, appointment_id = _booked(world)
    clinic_id, ids = world.a.clinic.id, Uuid7Generator()
    now = datetime.now(UTC)

    with uow_factory() as uow:
        again = publish(
            uow, AppointmentBooked(UUID(appointment_id)), clinic_id=clinic_id, ids=ids, now=now
        )
        uow.commit()
    assert again == 0
    assert _count(db, "appointment.booked") == 1
    assert _jobs(db, f"booking_confirmed:{appointment_id}") == 1

    with uow_factory() as uow:
        written = publish(
            uow, AppointmentCancelled(UUID(appointment_id)), clinic_id=clinic_id, ids=ids, now=now
        )
        assert written == 1
        # No commit: the change it was part of did not happen, so neither did the event.
    assert _count(db, "appointment.cancelled") == 0


def test_fr_ntf_02_the_member_who_made_the_change_is_not_told(
    world: World, db: Engine, uow_factory: UowFactory
) -> None:
    _, appointment_id = _booked(world)
    with uow_factory() as uow:
        written = publish(
            uow,
            AppointmentCancelled(UUID(appointment_id)),
            clinic_id=world.a.clinic.id,
            ids=Uuid7Generator(),
            now=datetime.now(UTC),
            actor_user_id=world.a.doctor_user.id,
        )
        uow.commit()
    assert written == 0
    assert _count(db, "appointment.cancelled") == 0


def test_fr_ntf_02_arrivals_walk_ins_and_cancellations_tell_the_doctor(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    arriving = _book(world, desk, session["id"], "Bina Shah")
    cancelling = _book(world, desk, session["id"], "Chetan Rao")

    moved = _send(
        desk,
        "POST",
        f"/api/v1/appointments/{arriving}/transitions",
        {"from": "BOOKED", "to": "ARRIVED"},
    )
    assert moved.status_code == 200, moved.get_json()
    walk_in = _send(
        desk,
        "POST",
        "/api/v1/queue/walk-ins",
        {"doctor_id": str(world.a.doctor.id), "patient_id": _patient(desk, "Divya Iyer")},
    )
    assert walk_in.status_code == 201, walk_in.get_json()
    cancelled = _send(
        desk, "POST", f"/api/v1/appointments/{cancelling}/cancel", {"reason": "PATIENT_REQUEST"}
    )
    assert cancelled.status_code == 200, cancelled.get_json()

    titles = {
        (i["kind"], i["title"].split(" · ")[0])
        for i in _items(world.client_for(world.a.doctor_user))
    }
    assert titles == {
        ("appointment.booked", "Bina"),
        ("appointment.booked", "Chetan"),
        ("appointment.arrived", "Bina"),
        ("appointment.arrived", "Divya"),
        ("appointment.cancelled", "Chetan"),
    }


def test_fr_ntf_04_a_failed_message_tells_the_desk_and_the_owners_once(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, appointment_id = _booked(world)
    rig = _rig(session_factory)
    rig.provider.script = [_raise(ProviderRefused(MSG_RECIPIENT_INVALID))]
    with pytest.raises(JobFailure):
        rig.booking(_job(db, f"booking_confirmed:{appointment_id}"))
    rig.booking(_job(db, f"booking_confirmed:{appointment_id}"))  # a replay: already settled

    for user in (world.a.desk, world.a.owner):
        [failed] = [i for i in _items(world.client_for(user)) if i["kind"] == "message.failed"]
        assert re.fullmatch(r"A message to Asha · \S+ could not be delivered", failed["title"])
        assert failed["link"].startswith("/patients/")
        assert failed["entity_type"] == "message"
    doctor_kinds = {i["kind"] for i in _items(world.client_for(world.a.doctor_user))}
    assert "message.failed" not in doctor_kinds
    with db.connect() as conn:
        told = conn.execute(
            text(
                "SELECT count(*) FROM clinic_memberships WHERE clinic_id = :c"
                " AND status = 'ACTIVE' AND role IN ('OWNER', 'FRONT_DESK')"
            ),
            {"c": world.a.clinic.id},
        ).scalar_one()
    assert _count(db, "message.failed") == told


def test_fr_ntf_02_an_accepted_invitation_tells_the_owners(world: World) -> None:
    owner = world.client_for(world.a.owner)
    invited = _send(
        owner,
        "POST",
        "/api/v1/clinic/staff",
        {"full_name": "Phone Desk", "role": "FRONT_DESK", "phone": "9000077101"},
    )
    assert invited.status_code == 201, invited.get_json()
    token = invited.get_json()["accept_url"].rsplit("/", 1)[1]

    joiner = world.anonymous()
    accepted = joiner.post(f"/api/v1/auth/invites/{token}/accept", json={"password": PASSWORD})
    assert accepted.status_code == 200, accepted.get_json()

    [joined] = [i for i in _items(owner) if i["kind"] == "staff.joined"]
    assert joined["title"] == "Phone Desk joined the team as front desk"
    assert (joined["link"], joined["entity_id"]) == ("/team", invited.get_json()["membership_id"])
    assert _items(joiner) == []


def test_fr_ntf_02_a_reschedule_tells_the_doctor_and_confirms_the_new_booking(
    world: World, db: Engine
) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    monday, tuesday = _session(desk, world, MONDAY), _session(desk, world, TUESDAY)
    booked = _send(
        desk,
        "POST",
        "/api/v1/appointments",
        {"session_id": monday["id"], "patient_id": _consenting_patient(desk, "Asha Rao")},
    )
    assert booked.status_code == 201, booked.get_json()
    first = booked.get_json()["id"]

    moved = _send(
        desk, "POST", f"/api/v1/appointments/{first}/reschedule", {"session_id": tuesday["id"]}
    )
    assert moved.status_code == 201, moved.get_json()
    new_id_ = str(moved.get_json()["id"])

    items = _items(world.client_for(world.a.doctor_user))
    [move] = [i for i in items if i["kind"] == "appointment.rescheduled"]
    assert re.fullmatch(r"Asha · \S+ moved to \d{1,2} [A-Z][a-z]{2}, token 1", move["title"])
    assert (move["entity_id"], move["link"]) == (new_id_, f"/queue?date={TUESDAY.isoformat()}")
    # The patient's WhatsApp confirmation for the new booking: the M5 job and key, unchanged.
    assert _jobs(db, f"booking_confirmed:{new_id_}") == 1


# --- Preferences (FR-NTF-05) --------------------------------------------------------------------


def test_fr_ntf_05_a_doctor_who_turns_bookings_off_is_not_told_and_the_change_is_audited(
    world: World, db: Engine
) -> None:
    doctor = world.client_for(world.a.doctor_user)
    defaults = doctor.get(f"{NOTIFICATIONS}/preferences").get_json()["items"]
    assert {p["kind"] for p in defaults} == {k.value for k in NotificationKind}
    assert all(p["enabled"] and p["channel"] == "IN_APP" for p in defaults)

    off = {"items": [{"kind": "appointment.booked", "enabled": False}]}
    changed = _send(doctor, "PUT", f"{NOTIFICATIONS}/preferences", off)
    assert changed.status_code == 200, changed.get_json()
    states = {p["kind"]: p["enabled"] for p in changed.get_json()["items"]}
    assert states["appointment.booked"] is False and states["appointment.arrived"] is True
    assert _send(doctor, "PUT", f"{NOTIFICATIONS}/preferences", off).status_code == 200

    _booked(world)
    assert _items(doctor) == []
    with db.connect() as conn:
        events = conn.execute(
            text("SELECT entity_id, metadata FROM audit_events WHERE action = :a"),
            {"a": "notification.preferences_changed"},
        ).all()
    # Once: the repeat changed nothing. The metadata names kinds, nothing about a patient.
    assert [(str(e.entity_id), dict(e.metadata)) for e in events] == [
        (str(world.a.doctor_user.id), {"on": "", "off": "appointment.booked"})
    ]


def test_fr_ntf_05_preferences_are_in_app_only_and_validated(world: World) -> None:
    doctor = world.client_for(world.a.doctor_user)
    whatsapp = {"items": [{"kind": "appointment.booked", "channel": "WHATSAPP", "enabled": False}]}
    resp = _send(doctor, "PUT", f"{NOTIFICATIONS}/preferences", whatsapp)
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["error"]["code"] == "CLN_INVALID_TRANSITION"
    for body in ({"items": []}, {"items": [{"kind": "visit.completed", "enabled": False}]}):
        assert _send(doctor, "PUT", f"{NOTIFICATIONS}/preferences", body).status_code == 422


# --- The centre (FR-NTF-03) ---------------------------------------------------------------------


def test_fr_ntf_03_summary_read_and_read_all(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    session = running_session(owner, world.a.doctor.id)
    for name in ("Asha Rao", "Bina Shah"):
        _book(world, desk, session["id"], name)

    summary = doctor.get(f"{NOTIFICATIONS}/summary")
    first, second = _items(doctor)
    assert summary.get_json() == {"unread": 2, "latest_id": first["id"]}
    etag = summary.headers["ETag"]
    assert (
        doctor.get(f"{NOTIFICATIONS}/summary", headers={"If-None-Match": etag}).status_code == 304
    )

    # Another member's notification is not found, whoever asks.
    stranger = _send(desk, "POST", f"{NOTIFICATIONS}/{first['id']}/read")
    assert stranger.status_code == 404
    assert stranger.get_json()["error"]["code"] == "REQ_NOT_FOUND"

    read = _send(doctor, "POST", f"{NOTIFICATIONS}/{first['id']}/read")
    assert read.status_code == 200 and read.get_json()["read_at"] is not None
    again = _send(doctor, "POST", f"{NOTIFICATIONS}/{first['id']}/read")
    assert again.get_json()["read_at"] == read.get_json()["read_at"]
    changed = doctor.get(f"{NOTIFICATIONS}/summary", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.get_json()["unread"] == 1

    everything = _send(doctor, "POST", f"{NOTIFICATIONS}/read-all")
    assert everything.get_json() == {"updated": 1}
    assert _unread(doctor) == 0
    assert all(i["read_at"] for i in _items(doctor))
    assert second["id"] in {i["id"] for i in _items(doctor)}


@pytest.mark.parametrize("limit", ["0", "51", "many"])
def test_fr_ntf_03_the_list_limit_is_bounded(world: World, limit: str) -> None:
    resp = world.client_for(world.a.doctor_user).get(f"{NOTIFICATIONS}?limit={limit}")
    assert resp.status_code == 422, resp.get_json()


def test_fr_ntf_03_the_centre_needs_a_clinic_session(world: World) -> None:
    assert world.anonymous().get(f"{NOTIFICATIONS}/summary").status_code == 401


# --- Volume (decision 8A) -----------------------------------------------------------------------


def test_a_dispatch_costs_one_query_per_lookup_whatever_the_recipients(
    world: World, db: Engine, uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    """MessageFailed to every owner and desk: patient, members, their choices, one insert."""
    _, appointment_id = _booked(world)
    with db.connect() as conn:
        patient_id = conn.execute(
            text("SELECT patient_id FROM appointments WHERE id = :a"), {"a": appointment_id}
        ).scalar_one()
    statements: list[str] = []

    def count(*args: Any) -> None:
        statements.append(str(args[2]).split()[0])

    engine = session_factory.kw["bind"]
    with uow_factory() as uow:
        uow.tenant(world.a.clinic.id).patients.get(patient_id)  # the transaction is open
        event.listen(engine, "before_cursor_execute", count)
        try:
            written = publish(
                uow,
                MessageFailed(new_id(), patient_id),
                clinic_id=world.a.clinic.id,
                ids=Uuid7Generator(),
                now=datetime.now(UTC),
            )
        finally:
            event.remove(engine, "before_cursor_execute", count)
    assert written >= 2  # every owner and the desk
    assert statements == ["SELECT", "SELECT", "SELECT", "INSERT"]


# --- Retention (decision 8A) --------------------------------------------------------------------


def test_notifications_older_than_90_days_are_purged(
    world: World, uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    def one(age: timedelta) -> Notification:
        return Notification.create(
            id=new_id(),
            clinic_id=world.a.clinic.id,
            recipient_user_id=world.a.owner.id,
            kind=NotificationKind.STAFF_JOINED,
            event_key=f"staff.joined:{new_id()}",
            title="Phone Desk joined the team as front desk",
            link="/team",
            entity_type="clinic_membership",
            entity_id=new_id(),
            now=NOW - age,
        )

    old, recent = one(timedelta(days=91)), one(timedelta(days=89))
    with uow_factory() as uow:
        assert uow.tenant(world.a.clinic.id).notifications.add_many([old, recent]) == 2
        uow.commit()

    counts = PurgeExpired(uow=uow_factory(), clock=FakeClock(NOW), ids=FakeIds()).execute()

    assert counts.notifications == 1
    with session_factory() as session:
        left = set(session.scalars(text("SELECT id FROM notifications")))
    assert left == {recent.id}
