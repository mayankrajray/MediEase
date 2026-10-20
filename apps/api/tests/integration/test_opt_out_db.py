"""Opting out by replying STOP, end to end on PostgreSQL (M5-P5).

FR-MSG-05; spec R14, AC5, §8 (a shared phone); decisions 1A-3A. A message is sent through the
real send jobs with a scripted provider, the STOP is posted signed to the webhook, and the
processing and confirmation jobs run as the worker would run them.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.messaging.catalog import YamlTemplateCatalog
from mediease_api.application.messaging.opt_out import SendOptOutConfirmation
from mediease_api.application.messaging.sender import MessageSender
from mediease_api.domain.messaging.errors import WH_STOP_UNMATCHED
from tests.conftest import LogReader, World
from tests.fakes import FakeClock
from tests.integration.test_messaging_db import (
    ScriptedProvider,
    _booked,
    _job,
    _messages,
    _rig,
)
from tests.integration.test_reminders_http import _issued, _reminders, _sender, _today
from tests.integration.test_visits_http import _send
from tests.integration.test_webhooks_http import CIPHER, _event_id, _post, _process
from tests.integration.test_webhooks_http import hooks as hooks  # the signed-webhook app


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _stop(
    phone: str | None,
    *,
    message_id: str = "wamid.STOP1",
    body: str = "Stop ",
    context: str | None = None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": message_id,
        "timestamp": str(int(datetime.now(UTC).timestamp())),
        "type": "text",
        "text": {"body": body},
    }
    if phone is not None:
        raw["from"] = phone.removeprefix("+")
    if context is not None:
        raw["context"] = {"id": context}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "contacts": [{"profile": {"name": "Sample Person"}}],
                            "messages": [raw],
                        },
                    }
                ]
            }
        ],
    }


def _one(db: Engine, sql: str, **params: Any) -> Any:
    with db.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def _phone(db: Engine, patient_id: object) -> str:
    return str(_one(db, "SELECT phone_e164 FROM patients WHERE id = :i", i=patient_id))


def _opted_out(db: Engine, patient_id: object) -> bool:
    return _one(db, "SELECT opted_out_at FROM patients WHERE id = :i", i=patient_id) is not None


def _payload(db: Engine, body: bytes) -> str:
    return json.dumps(
        _one(db, "SELECT payload FROM webhook_events WHERE id = :i", i=_event_id(db, body))
    )


def _confirmations(session_factory: sessionmaker[Session], clock: Any = None) -> Any:
    provider = ScriptedProvider()
    sender = MessageSender(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=clock or FakeClock(datetime.now(UTC)),
        ids=Uuid7Generator(),
        messaging=provider,
        templates=YamlTemplateCatalog.from_package(),
        phones=CIPHER,
    )
    return SendOptOutConfirmation(sender=sender), provider


def _register(client: FlaskClient, name: str, phone: str) -> str:
    resp = _send(
        client,
        "POST",
        "/api/v1/patients",
        {
            "full_name": name,
            "phone": phone,
            "sex": "UNDISCLOSED",
            "date_of_birth": "1990-05-17",
            "confirm_new": True,
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["id"])


def test_fr_msg_05_ac5_a_stop_opts_out_confirms_and_skips_the_next_reminder(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, visit, rx = _issued(world, _today() + timedelta(days=5))
    _rig(session_factory, cipher=CIPHER).rx_link(_job(db, f"rx_link:{rx['id']}"))
    patient_id = visit["patient_id"]
    phone = _phone(db, patient_id)

    status, body = _post(hooks, _stop(phone))
    assert status == 200
    stored = _payload(db, body)
    assert phone[1:] not in stored and "Sample Person" not in stored and "Stop" not in stored
    assert "from_encrypted" in stored  # decision 1A: only until processed

    _process(session_factory, db, body)
    assert _opted_out(db, patient_id)
    assert "from_encrypted" not in _payload(db, body)
    assert (
        _one(db, "SELECT error_code FROM webhook_events WHERE id = :i", i=_event_id(db, body))
        is None
    )
    audit = _one(
        db,
        "SELECT count(*) FROM audit_events WHERE action = 'patient.opted_out'"
        " AND actor_type = 'SYSTEM' AND entity_id = :i AND metadata->>'source' = 'inbound_message'",
        i=patient_id,
    )
    assert audit == 1

    key = f"opt_out_confirmed:{world.a.clinic.id}:wamid.STOP1"
    job = _job(db, key)
    assert (job.kind, job.clinic_id) == ("send_opt_out_confirmation", world.a.clinic.id)
    confirm, provider = _confirmations(session_factory)
    confirm(job)
    [call] = provider.calls
    assert (call.template.key, call.variables) == (
        "opt_out_confirmed",
        {"clinic_name": world.a.clinic.name},
    )
    assert call.to.e164 == phone
    [row] = _messages(db, key)
    assert (row.status, row.source_type, str(row.source_id)) == ("SENT", "OPT_OUT", patient_id)

    # AC5: the scheduled follow-up reminder is now skipped, with no message.
    [reminder] = _reminders(db, source_id=UUID(rx["id"]))
    send, reminders = _sender(session_factory, FakeClock(reminder.due_at))
    send(_job(db, f"reminder:{reminder.id}:1"))
    assert reminders.calls == []
    assert _reminders(db, id=reminder.id)[0].status == "SKIPPED_NO_CONSENT"

    # A second STOP changes nothing but is answered again (decision 3A).
    _, again = _post(hooks, _stop(phone, message_id="wamid.STOP2", body="STOP"))
    _process(session_factory, db, again)
    assert (
        _one(
            db,
            "SELECT count(*) FROM audit_events WHERE action = 'patient.opted_out'"
            " AND entity_id = :i",
            i=patient_id,
        )
        == 1
    )
    assert _job(db, f"opt_out_confirmed:{world.a.clinic.id}:wamid.STOP2").kind == job.kind


def test_decision_2a_a_shared_phone_opts_out_the_family_in_clinics_that_wrote_to_it(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, appointment_id = _booked(world)
    _rig(session_factory, cipher=CIPHER).booking(_job(db, f"booking_confirmed:{appointment_id}"))
    messaged = _one(db, "SELECT patient_id FROM appointments WHERE id = :i", i=appointment_id)
    phone = _phone(db, messaged)
    sibling = _register(world.client_for(world.a.desk), "Ravi Rao", phone)
    elsewhere = _register(world.client_for(world.b.desk), "Asha Rao", phone)  # never written to

    _, body = _post(hooks, _stop(phone, body="बंद"))
    _process(session_factory, db, body)

    assert _opted_out(db, messaged) and _opted_out(db, sibling)
    assert not _opted_out(db, elsewhere)
    jobs = _one(
        db,
        "SELECT count(*) FROM jobs WHERE kind = 'send_opt_out_confirmation' AND dedupe_key LIKE :k",
        k="%:wamid.STOP1",
    )
    assert jobs == 1  # one reply per clinic, not per patient


def test_r14_a_stop_without_a_number_is_matched_through_the_message_it_answers(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, appointment_id = _booked(world)
    key = f"booking_confirmed:{appointment_id}"
    _rig(session_factory, cipher=CIPHER).booking(_job(db, key))
    [row] = _messages(db, key)

    _, body = _post(hooks, _stop(None, context=row.provider_message_id))
    _process(session_factory, db, body)
    assert _opted_out(db, row.patient_id)


def test_r14_an_unknown_sender_changes_nothing_and_is_recorded(
    hooks: FlaskClient, db: Engine, session_factory: sessionmaker[Session], json_logs: LogReader
) -> None:
    before = _one(db, "SELECT count(*) FROM patients WHERE opted_out_at IS NOT NULL")
    _, body = _post(hooks, _stop("+919999999999", message_id="wamid.NOBODY"))
    _process(session_factory, db, body)
    assert _one(db, "SELECT count(*) FROM patients WHERE opted_out_at IS NOT NULL") == before
    event = _event_id(db, body)
    assert _one(db, "SELECT error_code FROM webhook_events WHERE id = :i", i=event) == (
        WH_STOP_UNMATCHED
    )
    assert _one(db, "SELECT count(*) FROM jobs WHERE dedupe_key LIKE '%wamid.NOBODY'") == 0
    [log] = [e for e in json_logs() if e["event"] == "webhook.stop_unmatched"]
    assert log["had_number"] is True and "999999" not in json.dumps(log)


def test_decision_3a_no_reply_once_the_service_window_has_closed(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, appointment_id = _booked(world)
    _rig(session_factory, cipher=CIPHER).booking(_job(db, f"booking_confirmed:{appointment_id}"))
    phone = _phone(
        db, _one(db, "SELECT patient_id FROM appointments WHERE id = :i", i=appointment_id)
    )
    _, body = _post(hooks, _stop(phone))
    _process(session_factory, db, body)
    key = f"opt_out_confirmed:{world.a.clinic.id}:wamid.STOP1"
    confirm, provider = _confirmations(
        session_factory, FakeClock(datetime.now(UTC) + timedelta(hours=25))
    )
    confirm(_job(db, key))
    assert provider.calls == [] and _messages(db, key) == []
