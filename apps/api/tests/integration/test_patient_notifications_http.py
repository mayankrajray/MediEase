"""Patient notifications and the live token link over HTTP (M6b-P6; portal R55-R72, AC23-AC28).

Real PostgreSQL, the real composition root. Booking requests come from the clinic's own
availability (``tests/booking_helpers.py``).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.security.link_signer import HmacLinkSigner
from mediease_api.application.links.use_cases import LinkTokens
from mediease_api.application.portal.medicine_due import notify_due
from mediease_api.application.portal.patient_email import SendPatientEmail
from mediease_api.domain.jobs.job import PATIENT_EMAIL_KIND, ClaimedJob
from mediease_api.domain.links.token import QueueClaims
from mediease_api.ports.email import EmailMessage
from tests.booking_helpers import offers, propose, request_in, staff_post
from tests.conftest import UowFactory, World
from tests.integration.test_appointments_http import _book, _patient, _schedule, _session
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_visits_http import _move
from tests.portal_helpers import PORTAL, link_by_invite
from tests.sessions_now import running_session

STAFF = "/api/v1/booking-requests"
NEW = {"new_patient": {"sex": "FEMALE", "age_years": 34}}
NOTE = "synthetic-staff-note-marker"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _notices(client: FlaskClient) -> list[dict[str, Any]]:
    resp = client.get(f"{PORTAL}/notifications")
    assert resp.status_code == 200, resp.get_json()
    return list(resp.get_json()["items"])


def _scalar(db: Engine, sql: str, **params: object) -> Any:
    with db.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _desk(world: World) -> FlaskClient:
    return world.client_for(world.a.desk)


def _put(client: FlaskClient, body: dict[str, Any]) -> Any:
    return client.put(f"{PORTAL}/notification-preferences", json=body, headers=portal_csrf(client))


# --- Booking answers (R56, R57, AC23) -----------------------------------------------------------


def test_ac23_accept_tells_the_requester_once_and_a_replay_adds_nothing(
    world: World, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rid = request_in(world, world.a, "told.accept@example.test")
    accepted = staff_post(_desk(world), f"{STAFF}/{rid}/accept", NEW)
    assert accepted.status_code == 201, accepted.get_json()
    [notice] = _notices(patient)
    assert notice["kind"] == "booking.accepted"
    assert notice["title"].startswith("Booked: ") and world.a.clinic.name in notice["title"]
    assert notice["read_at"] is None and notice["link"] == "/portal/appointments"
    # The appointment the request became is not told twice (no appointment.confirmed).
    assert _scalar(db, "SELECT count(*) FROM patient_notifications") == 1

    # R58: replaying the event writes nothing new (the database decides).
    from mediease_api.application.notifications.service import publish
    from mediease_api.domain.notifications.events import BookingRequestAnswered

    with uow_factory() as uow:
        publish(
            uow,
            BookingRequestAnswered(UUID(rid)),
            clinic_id=world.a.clinic.id,
            ids=Uuid7Generator(),
            now=SystemClock().now(),
        )
        uow.commit()
    assert _scalar(db, "SELECT count(*) FROM patient_notifications") == 1
    assert _scalar(db, "SELECT count(*) FROM jobs WHERE kind = :k", k=PATIENT_EMAIL_KIND) == 1


def test_ac23_propose_then_decline_by_the_patient_tells_only_the_proposal(
    world: World, db: Engine
) -> None:
    patient, rid = request_in(world, world.a, "told.propose@example.test")
    first = offers(world, world.a)[0]
    assert propose(world, world.a, rid, first["starts_at"]).status_code == 200
    [notice] = _notices(patient)
    assert notice["kind"] == "booking.proposed" and "suggests another time" in notice["title"]
    no = patient.post(
        f"{PORTAL}/booking-requests/{rid}/decline-proposal", headers=portal_csrf(patient)
    )
    assert no.status_code == 200
    assert len(_notices(patient)) == 1  # the patient's own choice is not told back


def test_ac25_r63_a_decline_names_the_reason_in_the_app_and_never_in_the_email(
    world: World, db: Engine, uow_factory: UowFactory, json_logs: Any
) -> None:
    patient, rid = request_in(world, world.a, "told.decline@example.test")
    resp = staff_post(
        _desk(world), f"{STAFF}/{rid}/decline", {"reason": "DOCTOR_UNAVAILABLE", "note": NOTE}
    )
    assert resp.status_code == 200
    [notice] = _notices(patient)
    assert "the doctor is not available then" in notice["title"]
    assert NOTE not in json.dumps(notice)

    sent: list[EmailMessage] = []

    class Capture:
        provider = "test"

        def send(self, message: EmailMessage) -> None:
            sent.append(message)

    with db.connect() as conn:
        job = conn.execute(
            text("SELECT id, clinic_id, payload FROM jobs WHERE kind = :k"),
            {"k": PATIENT_EMAIL_KIND},
        ).one()
    SendPatientEmail(uow=uow_factory(), email=Capture(), public_base_url="https://example.test")(
        ClaimedJob(
            id=job.id,
            kind=PATIENT_EMAIL_KIND,
            clinic_id=job.clinic_id,
            payload=job.payload,
            attempts=1,
            max_attempts=5,
            request_id=None,
            locked_by="test",
        )
    )
    [email] = sent
    assert email.subject.startswith(f"Booking declined at {world.a.clinic.name}")
    for leak in (NOTE, "doctor", "available", "9000000777"):
        assert leak not in email.text
    assert "https://example.test/portal/appointments" in email.text
    assert NOTE not in json.dumps(json_logs())


def test_r62_r63_switches_turn_off_the_app_notice_and_the_email(world: World, db: Engine) -> None:
    from tests.booking_helpers import verified_client

    patient = verified_client(world, "switches@example.test")
    assert (
        _put(
            patient, {"kind": "booking.accepted", "channel": "IN_APP", "enabled": False}
        ).status_code
        == 200
    )
    assert (
        _put(
            patient, {"kind": "booking.accepted", "channel": "EMAIL", "enabled": False}
        ).status_code
        == 200
    )
    refused = _put(patient, {"kind": "medicine.due", "channel": "EMAIL", "enabled": True})
    assert refused.status_code == 422
    prefs = {
        p["kind"]: p for p in patient.get(f"{PORTAL}/notification-preferences").get_json()["items"]
    }
    assert prefs["booking.accepted"] == {
        "kind": "booking.accepted",
        "in_app": False,
        "email": False,
    }
    assert prefs["medicine.due"]["email"] is None

    from tests.booking_helpers import ask, ensure_schedule

    ensure_schedule(world, world.a)
    made = ask(patient, world.a, offers(world, world.a)[0])
    assert made.status_code == 201
    assert (
        staff_post(_desk(world), f"{STAFF}/{made.get_json()['id']}/accept", NEW).status_code == 201
    )
    assert _notices(patient) == []
    assert _scalar(db, "SELECT count(*) FROM jobs WHERE kind = :k", k=PATIENT_EMAIL_KIND) == 0


# --- Appointments, the bell and unlinking (R56, R60, R67, R68, AC24) ----------------------------


def test_ac24_appointment_notices_follow_the_link_and_the_bell_counts(world: World) -> None:
    from tests.booking_helpers import verified_client

    owner, desk = world.client_for(world.a.owner), _desk(world)
    record = _patient(desk, "Linked Patient")
    patient = verified_client(world, "linked.bell@example.test")
    link = link_by_invite(owner, patient, record)
    _schedule(world)
    booked = _book(desk, _session(desk, world)["id"], record)
    assert booked.status_code == 201
    [notice] = _notices(patient)
    assert notice["kind"] == "appointment.confirmed"

    summary = patient.get(f"{PORTAL}/notifications/summary")
    assert summary.get_json()["unread"] == 1
    again = patient.get(
        f"{PORTAL}/notifications/summary", headers={"If-None-Match": summary.headers["ETag"]}
    )
    assert again.status_code == 304
    read = patient.post(f"{PORTAL}/notifications/{notice['id']}/read", headers=portal_csrf(patient))
    assert read.status_code == 204
    assert patient.get(f"{PORTAL}/notifications/summary").get_json()["unread"] == 0

    # A cancellation is told too; read-all clears it.
    cancel = desk.post(
        f"/api/v1/appointments/{booked.get_json()['id']}/cancel",
        json={"reason": "CLINIC_REQUEST"},
        headers={"X-CSRF-Token": desk.get_cookie("me_csrf", path="/").value},  # type: ignore[union-attr]
    )
    assert cancel.status_code == 200, cancel.get_json()
    assert [n["kind"] for n in _notices(patient)] == [
        "appointment.cancelled",
        "appointment.confirmed",
    ]
    marked = patient.post(f"{PORTAL}/notifications/read-all", headers=portal_csrf(patient))
    assert marked.get_json() == {"marked": 1}

    # R60: unlinking hides that clinic's appointment notices.
    gone = patient.delete(f"{PORTAL}/links/{link['id']}", headers=portal_csrf(patient))
    assert gone.status_code in (200, 204), gone.get_json()
    assert _notices(patient) == []


def test_r56_a_record_with_no_linked_account_tells_nobody(world: World, db: Engine) -> None:
    desk = _desk(world)
    _schedule(world)
    assert (
        _book(desk, _session(desk, world)["id"], _patient(desk, "Unlinked One")).status_code == 201
    )
    assert _scalar(db, "SELECT count(*) FROM patient_notifications") == 0


# --- Medicine due (R65, R66, AC26) --------------------------------------------------------------


def test_ac26_one_medicine_notice_in_its_half_hour_none_twice_none_outside_the_course(
    world: World, uow_factory: UowFactory
) -> None:
    from tests.integration.test_medicine_plan_http import _planned

    _, patient, issued = _planned(world)
    tab = issued["items"][0]  # 1-1-0 after food for 5 days: MORNING and AFTERNOON
    zone = ZoneInfo(world.a.clinic.timezone)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    local = (now - timedelta(minutes=10)).astimezone(zone)
    if local.date() != now.astimezone(zone).date():
        pytest.skip("just after midnight: the reminder would fall on yesterday")
    choice = {
        "prescription_id": issued["id"],
        "item_id": tab["id"],
        "slot": "MORNING",
        "enabled": True,
        "remind_at": local.strftime("%H:%M"),
    }
    saved = patient.put(
        f"{PORTAL}/medicine-plan/reminders", json=choice, headers=portal_csrf(patient)
    )
    if saved.status_code == 422:
        pytest.skip("the current time is outside 05:00-23:30, where reminder times are allowed")
    assert saved.status_code == 200, saved.get_json()

    ids = Uuid7Generator()
    clinic = world.a.clinic
    for at in (now, now + timedelta(minutes=5)):
        with uow_factory() as uow:
            notify_due(uow, clinic.id, clinic.name, clinic.timezone, at, ids)
            uow.commit()
    notices = [n for n in _notices(patient) if n["kind"] == "medicine.due"]
    assert len(notices) == 1
    assert notices[0]["title"] == f"Morning medicines · {local.strftime('%H:%M')}"
    assert notices[0]["link"] == "/portal/medicines"
    assert tab["medicine_name"] not in json.dumps(notices)
    with uow_factory() as uow:  # 40 minutes later is too late; 90 days on is past the course
        assert (
            notify_due(
                uow, clinic.id, clinic.name, clinic.timezone, now + timedelta(minutes=40), ids
            )
            == 0
        )
        assert (
            notify_due(uow, clinic.id, clinic.name, clinic.timezone, now + timedelta(days=90), ids)
            == 0
        )


# --- The live token link (R69-R72, AC27, AC28) --------------------------------------------------


def _tokens(world: World) -> LinkTokens:
    return LinkTokens(HmacLinkSigner(world.app.config["SETTINGS"].patient_link_keys()))


def test_ac27_the_live_page_moves_with_the_queue(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), _desk(world)
    session = running_session(owner, world.a.doctor.id)
    booked = [
        _book(desk, session["id"], _patient(desk, f"Queue Person{n}")).get_json()["id"]
        for n in range(3)
    ]
    link = desk.get(f"/api/v1/appointments/{booked[2]}/live-link")
    assert link.status_code == 200, link.get_json()
    path = "/api/v1/public/queue/" + link.get_json()["url"].rsplit("/q/", 1)[1]
    anon = world.anonymous()
    first = anon.get(path)
    assert first.status_code == 200
    body = first.get_json()
    from mediease_api.delivery.http.public_queue import LIVE_FIELDS

    assert set(body) == LIVE_FIELDS
    assert (body["state"], body["ahead"], body["now_seeing_token"]) == ("WAITING", 2, None)
    assert (
        first.headers["Cache-Control"] == "no-store" and "noindex" in first.headers["X-Robots-Tag"]
    )
    assert anon.get(path, headers={"If-None-Match": first.headers["ETag"]}).status_code == 304

    for appointment in booked[:1]:
        _move(desk, appointment, "BOOKED", "ARRIVED")
        _move(desk, appointment, "ARRIVED", "IN_CONSULTATION")
    moved = anon.get(path).get_json()
    assert (moved["ahead"], moved["now_seeing_token"]) == (1, body["token_number"] - 2)
    for name in ("Queue Person", "+91", "reason"):
        assert name not in json.dumps(moved)
    _move(desk, booked[2], "BOOKED", "ARRIVED")
    _move(desk, booked[2], "ARRIVED", "IN_CONSULTATION")
    assert anon.get(path).get_json()["state"] == "YOUR_TURN"


def test_ac28_an_expired_or_forged_link_is_refused(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), _desk(world)
    session = running_session(owner, world.a.doctor.id)
    appointment = _book(desk, session["id"], _patient(desk, "Old Link")).get_json()["id"]
    now = datetime.now(UTC).replace(microsecond=0)
    yesterday = _tokens(world).queue_token(
        QueueClaims(
            cid=world.a.clinic.id,
            aid=UUID(appointment),
            nbf=now - timedelta(days=2),
            exp=now - timedelta(days=1),
        )
    )
    anon = world.anonymous()
    expired = anon.get(f"/api/v1/public/queue/{yesterday}")
    assert (expired.status_code, expired.get_json()["error"]["code"]) == (410, "LINK_EXPIRED")
    forged = anon.get(f"/api/v1/public/queue/{yesterday[:-4]}AAAA")
    assert (forged.status_code, forged.get_json()["error"]["code"]) == (404, "LINK_INVALID")
    # A cancelled appointment gets no new link.
    cancel = desk.post(
        f"/api/v1/appointments/{appointment}/cancel",
        json={"reason": "CLINIC_REQUEST"},
        headers={"X-CSRF-Token": desk.get_cookie("me_csrf", path="/").value},  # type: ignore[union-attr]
    )
    assert cancel.status_code == 200
    assert desk.get(f"/api/v1/appointments/{appointment}/live-link").status_code == 422
