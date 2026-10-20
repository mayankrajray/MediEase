"""Message costs and the ops monthly total on PostgreSQL (M5-P5; spec R18; decisions 5A-7A).

A booking confirmation is sent through the real job with a scripted WhatsApp provider; its status
webhook then prices it. The ops total reads every clinic's messages of a month in its own zone.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.messaging.catalog import YamlTemplateCatalog
from mediease_api.adapters.messaging.prices import load_price_table
from mediease_api.adapters.messaging.whatsapp_webhook import WhatsAppWebhookParser
from mediease_api.application.messaging.booking import SendBookingConfirmation
from mediease_api.application.messaging.opt_out import OptOutByReply
from mediease_api.application.messaging.sender import MessageSender
from mediease_api.application.messaging.webhooks import ProcessWebhookEvent
from mediease_api.domain.messaging.message import Channel
from tests.conftest import World
from tests.integration.test_messaging_db import ScriptedProvider, _booked, _job, _messages
from tests.integration.test_webhooks_http import CIPHER, _document, _event_id, _post, _status
from tests.integration.test_webhooks_http import hooks as hooks  # the signed-webhook app
from tests.sessions_now import running_session

IDS = Uuid7Generator()
PRICES = load_price_table()
COSTS = "/api/v1/ops/messaging-costs"


@dataclass
class WhatsAppScripted(ScriptedProvider):
    @property
    def channel(self) -> Channel:
        return Channel.WHATSAPP


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _sent(world: World, db: Engine, session_factory: sessionmaker[Session], **booked: Any) -> Any:
    _, appointment_id = _booked(world, **booked)
    key = f"booking_confirmed:{appointment_id}"
    sender = MessageSender(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=SystemClock(),
        ids=IDS,
        messaging=WhatsAppScripted(),
        templates=YamlTemplateCatalog.from_package(),
        phones=CIPHER,
        prices=PRICES,
    )
    SendBookingConfirmation(sender=sender)(_job(db, key))
    [row] = _messages(db, key)
    return row


def _deliver(
    hooks: FlaskClient, db: Engine, session_factory: sessionmaker[Session], *statuses: Any
) -> None:
    _, body = _post(hooks, _document(*statuses))
    ProcessWebhookEvent(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=SystemClock(),
        parser=WhatsAppWebhookParser(CIPHER),
        opt_outs=OptOutByReply(ids=IDS, phones=CIPHER),
        prices=PRICES,
    )(_job(db, f"process_webhook_event:{_event_id(db, body)}"))


def _cost(db: Engine, key: str) -> Any:
    [row] = _messages(db, key)
    return row.cost_millipaise


def test_r18_a_whatsapp_message_is_priced_when_its_delivery_is_reported(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    session = running_session(world.client_for(world.a.owner), world.a.doctor.id)
    paid = _sent(world, db, session_factory, session=session)
    free = _sent(world, db, session_factory, session=session)
    assert (paid.channel, paid.cost_millipaise) == ("WHATSAPP", None)  # not delivered yet

    pricing = {"category": "utility", "billable": True}
    _deliver(
        hooks,
        db,
        session_factory,
        _status(paid.provider_message_id, "sent", message_id=paid.id, pricing=pricing),
        _status(paid.provider_message_id, "delivered", message_id=paid.id, pricing=pricing),
        _status(
            free.provider_message_id,
            "delivered",
            message_id=free.id,
            pricing={"category": "utility", "billable": False},
        ),
    )
    assert _cost(db, paid.idempotency_key) == 11500  # 11.5 paise (2026 utility rate)
    assert _cost(db, free.idempotency_key) == 0
    # A later status never prices it twice.
    _deliver(hooks, db, session_factory, _status(paid.provider_message_id, "read"))
    assert _cost(db, paid.idempotency_key) == 11500


def test_decision_6a_a_failed_message_costs_nothing(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    row = _sent(world, db, session_factory)
    _deliver(
        hooks,
        db,
        session_factory,
        _status(row.provider_message_id, "failed", message_id=row.id, errors=[{"code": 131026}]),
    )
    assert _cost(db, row.idempotency_key) == 0


def _seed(db: Engine, clinic_id: Any, *, sent_at: datetime, cost: int | None, channel: str) -> None:
    """A sent message of the clinic's existing patient, at a chosen time and cost."""
    with db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO messages (id, clinic_id, patient_id, source_type, source_id,"
                " channel, provider, template_key, template_version, language, variables,"
                " to_phone_encrypted, idempotency_key, status, provider_message_id,"
                " cost_millipaise, sent_at, created_at, updated_at)"
                " SELECT gen_random_uuid(), :c, p.id, 'REMINDER', gen_random_uuid(), :ch, 'x',"
                " 'follow_up_due', 1, 'en', '{}'::jsonb, 'x', gen_random_uuid()::text, 'SENT',"
                " gen_random_uuid()::text, :cost, :at, :at, :at"
                " FROM patients p WHERE p.clinic_id = :c LIMIT 1"
            ),
            {"c": clinic_id, "ch": channel, "cost": cost, "at": sent_at},
        )


def test_decision_7a_ops_see_each_clinics_month_in_its_own_zone_rounded_at_the_total(
    world: World, db: Engine
) -> None:
    _booked(world)  # clinic A has a patient
    clinic = world.a.clinic.id
    # 1 Oct 00:10 IST is 30 Sep 18:40 UTC: October in the clinic's zone.
    _seed(
        db,
        clinic,
        sent_at=datetime(2026, 9, 30, 18, 40, tzinfo=UTC),
        cost=11500,
        channel="WHATSAPP",
    )
    _seed(
        db, clinic, sent_at=datetime(2026, 10, 15, 6, 0, tzinfo=UTC), cost=11500, channel="WHATSAPP"
    )
    _seed(
        db, clinic, sent_at=datetime(2026, 10, 15, 6, 0, tzinfo=UTC), cost=None, channel="WHATSAPP"
    )
    _seed(db, clinic, sent_at=datetime(2026, 10, 31, 18, 31, tzinfo=UTC), cost=500, channel="SMS")
    # 30 Sep 18:20 UTC is 23:50 IST on 30 Sep: September, not counted.
    _seed(db, clinic, sent_at=datetime(2026, 9, 30, 18, 20, tzinfo=UTC), cost=99000, channel="SMS")

    ops = world.client_for(world.ops)
    resp = ops.get(f"{COSTS}?month=2026-10")
    assert resp.status_code == 200, resp.get_json()
    assert resp.headers["Cache-Control"] == "no-store"
    body = resp.get_json()
    [entry] = [c for c in body["clinics"] if c["clinic_id"] == str(clinic)]
    assert (entry["messages"], entry["unpriced"], entry["cost_paise"]) == (3, 1, 23)
    assert entry["channels"] == [
        {"channel": "WHATSAPP", "messages": 3, "priced": 2, "unpriced": 1, "cost_paise": 23},
    ]
    # 31 Oct 18:31 UTC is 1 Nov 00:01 IST: November.
    november = ops.get(f"{COSTS}?month=2026-11").get_json()
    [later] = [c for c in november["clinics"] if c["clinic_id"] == str(clinic)]
    assert later["channels"][0]["channel"] == "SMS" and later["cost_paise"] == 1
    assert body["month"] == "2026-10" and body["cost_paise"] >= 23
    for secret in ("follow_up_due", "patient", "+91"):
        assert secret not in resp.get_data(as_text=True)


@pytest.mark.parametrize("query", ["", "?month=2026-13", "?month=2026-1", "?month=oct"])
def test_decision_7a_the_month_is_required_as_yyyy_mm(world: World, query: str) -> None:
    resp = world.client_for(world.ops).get(f"{COSTS}{query}")
    assert (resp.status_code, resp.get_json()["error"]["code"]) == (422, "REQ_VALIDATION_FAILED")


def test_decision_7a_clinic_staff_cannot_read_the_ops_totals(world: World) -> None:
    resp = world.client_for(world.a.owner).get(f"{COSTS}?month=2026-10")
    assert resp.status_code == 403
