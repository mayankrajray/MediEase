"""M7e-E4 (spec web-push R40-R46): the clinic's reminders for patients who use the app.

Real PostgreSQL and the real composition root. Bookings go through HTTP so the reminders are made
in the booking's transaction; send jobs run as the worker would, with a scripted WhatsApp provider
and a fixed clock. The patient's account is linked to the record by the clinic's invitation.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.application.reminders.send import SendReminder
from mediease_api.domain.jobs.job import PUSH_KIND
from tests.booking_helpers import verified_client
from tests.conftest import World
from tests.fakes import FakeClock
from tests.integration.test_appointment_reminders_http import (
    _book,
    _consenting,
    _reminders,
    _sender,
)
from tests.integration.test_appointments_http import TUESDAY, _patient, _schedule, _session
from tests.integration.test_messaging_db import _job
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_push_http import PORTAL_DEVICES, subscribe, subscription
from tests.integration.test_visits_http import _send
from tests.portal_helpers import PORTAL, link_by_invite

PREFS = f"{PORTAL}/notification-preferences"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _rows(db: Engine, sql: str, **params: Any) -> list[Any]:
    with db.connect() as conn:
        return list(conn.execute(text(sql), params))


def _app_user(world: World, desk: FlaskClient, email: str, *, consent: bool) -> tuple[Any, str]:
    """A record linked to a verified app account: (the patient's portal client, record ID)."""
    record = _consenting(desk, "Asha Rao") if consent else _patient(desk, "Asha Rao")
    patient = verified_client(world, email)
    link_by_invite(world.client_for(world.a.owner), patient, record)
    return patient, record


def _notices(patient: FlaskClient) -> list[dict[str, Any]]:
    resp = patient.get(f"{PORTAL}/notifications")
    assert resp.status_code == 200, resp.get_json()
    return [n for n in resp.get_json()["items"] if n["kind"].endswith(("reminder", "due"))]


def _run(db: Engine, session_factory: sessionmaker[Session], reminder: Any) -> Any:
    sender, provider = _sender(session_factory, FakeClock(reminder.due_at))
    SendReminder(sender=sender, ids=Uuid7Generator())(_job(db, f"reminder:{reminder.id}:1"))
    return provider


# --- Appointment reminders (R40-R43) --------------------------------------------------------------


def test_r40_r43_an_app_user_without_whatsapp_is_reminded_in_the_app_once(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    patient, record = _app_user(world, desk, "app.reminded@example.test", consent=False)
    subscribe(patient, PORTAL_DEVICES, portal_csrf(patient), subscription(1))
    appointment = _book(desk, _session(desk, world, TUESDAY)["id"], record)

    # R40: the same two reminders a WhatsApp patient gets, at the same times.
    evening, before = _reminders(db, appointment)
    assert (evening.status, before.status) == ("SCHEDULED", "SCHEDULED")

    provider = _run(db, session_factory, evening)
    assert provider.calls == []  # WhatsApp unchanged: no consent, no message
    [notice] = _notices(patient)
    assert notice["kind"] == "appointment.reminder"
    assert notice["title"] == (
        f"Reminder: {TUESDAY.day} {TUESDAY.strftime('%b')}, token 1 with"
        f" {world.a.doctor.display_name} at {world.a.clinic.name}"
    )
    assert notice["link"] == "/portal/appointments"
    assert _reminders(db, appointment)[0].status == "SENT_IN_APP"
    # R41: and a push to the device (its booking confirmation had one too).
    reminded = "SELECT 1 FROM jobs WHERE kind = :k AND payload->>'notice' = 'appointment.reminder'"
    assert len(_rows(db, reminded, k=PUSH_KIND)) == 1

    # R42: the same job again tells nobody twice.
    _run(db, session_factory, evening)
    assert len(_notices(patient)) == 1
    assert len(_rows(db, reminded, k=PUSH_KIND)) == 1

    # Staff see it went, and are not asked to call.
    listed = desk.get(f"/api/v1/patients/{record}/reminders").get_json()["items"]
    assert {r["status"] for r in listed} == {"SENT_IN_APP", "SCHEDULED"}


def test_r42_a_consenting_app_user_gets_whatsapp_and_the_app(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    patient, record = _app_user(world, desk, "app.both@example.test", consent=True)
    evening = _reminders(db, _book(desk, _session(desk, world, TUESDAY)["id"], record))[0]

    provider = _run(db, session_factory, evening)
    [call] = provider.calls
    assert call.template.key == "appointment_reminder"
    assert [n["kind"] for n in _notices(patient)] == ["appointment.reminder"]
    assert _rows(db, "SELECT status FROM reminders WHERE id = :i", i=evening.id)[0].status == (
        "SENT"
    )


def test_r40_without_whatsapp_or_a_linked_account_still_nothing(world: World, db: Engine) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    appointment = _book(desk, _session(desk, world, TUESDAY)["id"], _patient(desk, "Bina Shah"))
    assert _reminders(db, appointment) == []


def test_r44_a_cancelled_appointment_reminds_nobody(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    patient, record = _app_user(world, desk, "app.cancelled@example.test", consent=False)
    appointment = _book(desk, _session(desk, world, TUESDAY)["id"], record)
    evening = _reminders(db, appointment)[0]
    cancelled = _send(
        desk, "POST", f"/api/v1/appointments/{appointment}/cancel", {"reason": "PATIENT_REQUEST"}
    )
    assert cancelled.status_code == 200
    _run(db, session_factory, evening)
    assert _notices(patient) == []
    assert {r.status for r in _reminders(db, appointment)} == {"CANCELLED"}


def test_r43_both_switches_off_means_not_reached(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _schedule(world)
    desk = world.client_for(world.a.desk)
    patient, record = _app_user(world, desk, "app.quiet@example.test", consent=False)
    for channel in ("IN_APP", "PUSH"):
        off = patient.put(
            PREFS,
            json={"kind": "appointment.reminder", "channel": channel, "enabled": False},
            headers=portal_csrf(patient),
        )
        assert off.status_code == 200, off.get_json()
    evening = _reminders(db, _book(desk, _session(desk, world, TUESDAY)["id"], record))[0]
    _run(db, session_factory, evening)
    assert _notices(patient) == []
    assert _reminders(db, str(evening.appointment_id))[0].status == "SKIPPED_NO_CONSENT"


# --- Follow-ups (R45) -----------------------------------------------------------------------------


def test_r45_a_follow_up_for_an_app_user_is_allowed_and_told_in_their_language(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    desk = world.client_for(world.a.desk)
    patient, record = _app_user(world, desk, "app.follow@example.test", consent=False)
    assert (
        patient.patch(
            f"{PORTAL}/me", json={"language": "hi"}, headers=portal_csrf(patient)
        ).status_code
        == 200
    )
    follow_up = TUESDAY + timedelta(days=7)
    created = _send(
        desk,
        "POST",
        f"/api/v1/patients/{record}/reminders",
        {"doctor_id": str(world.a.doctor.id), "follow_up_date": follow_up.isoformat()},
    )
    assert created.status_code == 201, created.get_json()  # was REM_NO_CONSENT before M7e-E4
    [reminder] = _rows(db, "SELECT * FROM reminders WHERE id = :i", i=created.get_json()["id"])

    provider = _run(db, session_factory, reminder)
    assert provider.calls == []
    [notice] = _notices(patient)
    assert notice["kind"] == "follow_up.due"
    months = ("जन॰", "फ़र॰", "मार्च", "अप्रैल", "मई", "जून", "जुल॰", "अग॰", "सित॰", "अक्टू॰", "नव॰", "दिस॰")
    assert notice["title"] == (
        f"{world.a.doctor.display_name} ({world.a.clinic.name}) के साथ फ़ॉलो-अप:"
        f" {follow_up.day} {months[follow_up.month - 1]}"
    )
    assert _rows(db, "SELECT status FROM reminders WHERE id = :i", i=reminder.id)[0].status == (
        "SENT_IN_APP"
    )


def test_r45_a_follow_up_without_whatsapp_or_the_app_is_still_refused(world: World) -> None:
    desk = world.client_for(world.a.desk)
    refused = _send(
        desk,
        "POST",
        f"/api/v1/patients/{_patient(desk, 'Chetan Rao')}/reminders",
        {
            "doctor_id": str(world.a.doctor.id),
            "follow_up_date": (TUESDAY + timedelta(days=7)).isoformat(),
        },
    )
    assert (refused.status_code, refused.get_json()["error"]["code"]) == (409, "REM_NO_CONSENT")
