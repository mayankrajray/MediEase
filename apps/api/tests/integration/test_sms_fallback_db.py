"""The SMS fallback for reminders on PostgreSQL (M5-P5; FR-REM-06; decision 4A).

A prescription is issued over HTTP so the reminder is made by the real use case; the reminder's
WhatsApp send fails through a scripted provider (or a later webhook), and the fallback job runs
with the console SMS adapter, as the worker would run both.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.messaging.catalog import YamlTemplateCatalog
from mediease_api.adapters.messaging.console_sms import ConsoleSmsAdapter
from mediease_api.adapters.messaging.whatsapp_webhook import WhatsAppWebhookParser
from mediease_api.application.messaging.opt_out import OptOutByReply
from mediease_api.application.messaging.sender import MessageSender
from mediease_api.application.messaging.webhooks import ProcessWebhookEvent
from mediease_api.application.reminders.fallback import SendSmsFallback, SmsFallback
from mediease_api.application.reminders.send import SendReminder
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.messaging.errors import (
    MSG_OUTCOME_UNKNOWN,
    MSG_RECIPIENT_INVALID,
    ProviderOutcomeUnknown,
    ProviderRefused,
)
from mediease_api.ports.messaging import MessagingPort
from tests.conftest import LogReader, World
from tests.fakes import FakeClock
from tests.integration.test_messaging_db import ScriptedProvider, _job, _messages, _raise
from tests.integration.test_reminders_http import _at_ist, _issued, _reminders, _today
from tests.integration.test_visits_http import _send
from tests.integration.test_webhooks_http import CIPHER, _document, _event_id, _post, _status
from tests.integration.test_webhooks_http import hooks as hooks  # the signed-webhook app

IDS = Uuid7Generator()


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _sender(session_factory: sessionmaker[Session], clock: Any, port: MessagingPort) -> Any:
    return MessageSender(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=clock,
        ids=IDS,
        messaging=port,
        templates=YamlTemplateCatalog.from_package(),
        phones=CIPHER,
    )


def _reminder(world: World, db: Engine, *, sms: bool = True) -> Any:
    _, visit, rx = _issued(world, _today() + timedelta(days=5))
    consent = _send(
        world.client_for(world.a.desk),
        "PUT",
        f"/api/v1/patients/{visit['patient_id']}/consent",
        {"whatsapp": True, "sms": sms},
    )
    assert consent.status_code == 200, consent.get_json()
    [reminder] = _reminders(db, source_id=UUID(rx["id"]))
    return reminder


def _fail_on_whatsapp(
    session_factory: sessionmaker[Session],
    db: Engine,
    reminder: Any,
    error: BaseException,
    *,
    fallback: bool = True,
) -> None:
    provider = ScriptedProvider(script=[_raise(error)])
    send = SendReminder(
        sender=_sender(session_factory, FakeClock(reminder.due_at), provider),
        ids=IDS,
        fallback=SmsFallback(ids=IDS) if fallback else None,
    )
    with pytest.raises(JobFailure):
        send(_job(db, f"reminder:{reminder.id}:1"))


def _fallback_jobs(db: Engine, reminder_id: object) -> list[Any]:
    with db.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT * FROM jobs WHERE kind = 'send_sms_fallback'"
                    " AND payload->>'reminder_id' = :r ORDER BY dedupe_key"
                ),
                {"r": str(reminder_id)},
            )
        )


def test_fr_rem_06_a_reminder_whatsapp_cannot_deliver_falls_back_to_one_sms(
    world: World, db: Engine, session_factory: sessionmaker[Session], json_logs: LogReader
) -> None:
    reminder = _reminder(world, db)
    _fail_on_whatsapp(session_factory, db, reminder, ProviderRefused(MSG_RECIPIENT_INVALID))
    [whatsapp] = _messages(db, f"follow_up_due:{reminder.id}")
    assert (whatsapp.status, whatsapp.error_code) == ("FAILED", MSG_RECIPIENT_INVALID)
    [queued] = _fallback_jobs(db, reminder.id)
    assert (queued.dedupe_key, queued.clinic_id) == (
        f"sms_fallback:{reminder.id}:0",
        world.a.clinic.id,
    )

    sms = ConsoleSmsAdapter()
    run = SendSmsFallback(sender=_sender(session_factory, FakeClock(reminder.due_at), sms), ids=IDS)
    run(_job(db, queued.dedupe_key))
    run(_job(db, queued.dedupe_key))  # again: still one SMS
    [row] = _messages(db, f"sms:{reminder.id}")
    assert (row.channel, row.provider, row.status, row.source_type, row.template_key) == (
        "SMS",
        "console",
        "SENT",
        "REMINDER",
        "follow_up_due",
    )
    # The reminder shows its latest message: the SMS (P4 decision 3A).
    patient_id = reminder.patient_id
    listed = world.client_for(world.a.desk).get(f"/api/v1/patients/{patient_id}/reminders")
    [item] = listed.get_json()["items"]
    assert item["status"] == "SENT"
    [log] = [e for e in json_logs() if e["event"] == "messaging.console_sms_accepted"]
    assert log["segments"] == 1 and log["to"].startswith("+91") and "*" in log["to"]


def test_fr_rem_06_off_by_default(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    off = _reminder(world, db)
    _fail_on_whatsapp(
        session_factory, db, off, ProviderRefused(MSG_RECIPIENT_INVALID), fallback=False
    )
    assert _fallback_jobs(db, off.id) == []


def test_fr_rem_06_never_after_an_unknown_outcome(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    unknown = _reminder(world, db)
    _fail_on_whatsapp(session_factory, db, unknown, ProviderOutcomeUnknown())
    [row] = _messages(db, f"follow_up_due:{unknown.id}")
    assert row.error_code == MSG_OUTCOME_UNKNOWN
    assert _fallback_jobs(db, unknown.id) == []  # it may have been delivered: at most once


def test_fr_rem_06_no_sms_without_sms_consent(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    refused = _reminder(world, db, sms=False)
    _fail_on_whatsapp(session_factory, db, refused, ProviderRefused(MSG_RECIPIENT_INVALID))
    [job] = _fallback_jobs(db, refused.id)
    sms = ConsoleSmsAdapter()
    SendSmsFallback(sender=_sender(session_factory, SystemClock(), sms), ids=IDS)(
        _job(db, job.dedupe_key)
    )
    assert _messages(db, f"sms:{refused.id}") == []


def test_fr_rem_06_the_sms_waits_out_the_quiet_hours(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    night = _reminder(world, db)
    _fail_on_whatsapp(session_factory, db, night, ProviderRefused(MSG_RECIPIENT_INVALID))
    [first] = _fallback_jobs(db, night.id)
    late = FakeClock(_at_ist(_today(), 22, 15))
    SendSmsFallback(sender=_sender(session_factory, late, ConsoleSmsAdapter()), ids=IDS)(
        _job(db, first.dedupe_key)
    )
    assert _messages(db, f"sms:{night.id}") == []
    _, deferred = _fallback_jobs(db, night.id)
    assert deferred.dedupe_key == f"sms_fallback:{night.id}:1"
    assert deferred.run_at == _at_ist(_today() + timedelta(days=1), 8)


def test_fr_rem_06_a_failure_reported_by_webhook_falls_back_too(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    reminder = _reminder(world, db)
    provider = ScriptedProvider()
    SendReminder(sender=_sender(session_factory, FakeClock(reminder.due_at), provider), ids=IDS)(
        _job(db, f"reminder:{reminder.id}:1")
    )
    [row] = _messages(db, f"follow_up_due:{reminder.id}")
    assert row.status == "SENT"

    _, body = _post(
        hooks,
        _document(
            _status(row.provider_message_id, "failed", message_id=row.id, errors=[{"code": 131026}])
        ),
    )
    process = ProcessWebhookEvent(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=SystemClock(),
        parser=WhatsAppWebhookParser(CIPHER),
        opt_outs=OptOutByReply(ids=IDS, phones=CIPHER),
        fallback=SmsFallback(ids=IDS),
    )
    process(_job(db, f"process_webhook_event:{_event_id(db, body)}"))
    [job] = _fallback_jobs(db, reminder.id)
    assert job.state == "queued"
