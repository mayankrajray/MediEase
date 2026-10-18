"""WhatsApp webhooks end to end on PostgreSQL (M5-P3; FR-MSG-03; spec R12, R13, R15; AC6).

Bookings and prescriptions go through HTTP, the send job runs with a scripted provider
(``test_messaging_db``), and the webhook is posted, signed, to an app wired with the WhatsApp
secrets; its processing job then runs as the worker would run it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.messaging.whatsapp_webhook import WhatsAppWebhookParser
from mediease_api.application.messaging.webhooks import ProcessWebhookEvent, ReconcileMessages
from mediease_api.bootstrap import create_app
from mediease_api.config.settings import AppEnv, AppSettings
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.messaging.errors import MSG_OUTCOME_UNKNOWN, WH_UNMATCHED
from tests.conftest import _BLOBS, CHEAP_HASHER, TEST_IP_SALT, TEST_SIGNING_KEY, LogReader, World
from tests.fakes import FakeClock
from tests.integration.test_messaging_db import (
    Crash,
    _booked,
    _issued_with_consent,
    _job,
    _link_delivery,
    _messages,
    _raise,
    _rig,
)

SECRET = "synthetic-app-secret-for-tests"
VERIFY = "synthetic-verify-token-01"
URL = "/webhooks/whatsapp"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def hooks(migrated_database_url: str, world: World) -> Iterator[FlaskClient]:
    """An app on the same database with the WhatsApp webhook secrets set."""
    settings = AppSettings(
        APP_ENV=AppEnv.LOCAL,
        DATABASE_URL=migrated_database_url,
        JWT_SIGNING_KEY=SecretStr(TEST_SIGNING_KEY),
        AUDIT_IP_SALT=SecretStr(TEST_IP_SALT),
        BLOB_LOCAL_DIR=_BLOBS.name,
        WHATSAPP_APP_SECRET=SecretStr(SECRET),
        WHATSAPP_VERIFY_TOKEN=SecretStr(VERIFY),
    )
    with create_app(settings, password_hasher=CHEAP_HASHER).test_client() as client:
        yield client


def _document(*statuses: dict[str, Any], text_message: bool = False) -> dict[str, Any]:
    value: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550001111", "phone_number_id": "1"},
        "statuses": list(statuses),
    }
    if text_message:
        value["contacts"] = [{"profile": {"name": "Sample Person"}, "wa_id": "919111111111"}]
        value["messages"] = [
            {
                "from": "919111111111",
                "id": "wamid.IN",
                "timestamp": "1",
                "type": "text",
                "text": {"body": "SENTINEL-inbound-text"},
            }
        ]
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": value}]}],
    }


def _status(
    provider_id: str,
    status: str,
    *,
    at: datetime | None = None,
    message_id: object = None,
    **extra: Any,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "id": provider_id,
        "status": status,
        "timestamp": str(int((at or datetime.now(UTC)).timestamp())),
        "recipient_id": "919111111111",
        **extra,
    }
    if message_id is not None:
        raw["biz_opaque_callback_data"] = str(message_id)
    return raw


def _post(
    client: FlaskClient, document: dict[str, Any], *, secret: str = SECRET
) -> tuple[int, bytes]:
    body = json.dumps(document).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    resp = client.post(
        URL,
        data=body,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )
    return resp.status_code, body


def _event_id(db: Engine, body: bytes) -> UUID:
    with db.connect() as conn:
        return UUID(
            str(
                conn.execute(
                    text("SELECT id FROM webhook_events WHERE event_key = :k"),
                    {"k": hashlib.sha256(body).hexdigest()},
                ).scalar_one()
            )
        )


def _count(db: Engine, sql: str, **params: Any) -> int:
    with db.connect() as conn:
        return int(conn.execute(text(sql), params).scalar_one())


def _process(session_factory: sessionmaker[Session], db: Engine, body: bytes, **job: Any) -> None:
    handler = ProcessWebhookEvent(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=SystemClock(),
        parser=WhatsAppWebhookParser(),
    )
    handler(_job(db, f"process_webhook_event:{_event_id(db, body)}", **job))


def _sent_booking(world: World, db: Engine, session_factory: sessionmaker[Session]) -> Any:
    _, appointment_id = _booked(world)
    key = f"booking_confirmed:{appointment_id}"
    _rig(session_factory).booking(_job(db, key))
    [row] = _messages(db, key)
    return row


# --- R12, R13, AC6 ------------------------------------------------------------------------------


def test_r12_the_subscription_challenge_needs_our_verify_token(hooks: FlaskClient) -> None:
    ok = hooks.get(f"{URL}?hub.mode=subscribe&hub.verify_token={VERIFY}&hub.challenge=1158201444")
    assert (ok.status_code, ok.get_data(as_text=True)) == (200, "1158201444")
    for query in (
        "hub.mode=subscribe&hub.verify_token=wrong-token-0000000&hub.challenge=1",
        f"hub.mode=unsubscribe&hub.verify_token={VERIFY}&hub.challenge=1",
        f"hub.mode=subscribe&hub.verify_token={VERIFY}&hub.challenge=<script>",
    ):
        refused = hooks.get(f"{URL}?{query}")
        assert (refused.status_code, refused.get_json()["error"]["code"]) == (
            403,
            "WH_VERIFY_FAILED",
        )


def test_ac6_a_bad_signature_is_401_and_nothing_is_stored(
    hooks: FlaskClient, world: World, db: Engine, json_logs: LogReader
) -> None:
    before = _count(db, "SELECT count(*) FROM webhook_events")
    status, _ = _post(hooks, _document(_status("wamid.X", "delivered")), secret="not-our-secret")
    assert status == 401
    unsigned = hooks.post(URL, data=b"{}", headers={"Content-Type": "application/json"})
    assert (unsigned.status_code, unsigned.get_json()["error"]["code"]) == (
        401,
        "WH_SIGNATURE_INVALID",
    )
    # The world app has no secret: it refuses even a correctly signed body.
    status, _ = _post(world.client_for(world.a.desk), _document())
    assert status == 401
    assert _count(db, "SELECT count(*) FROM webhook_events") == before
    assert [e for e in json_logs() if e["event"] == "webhook.signature_invalid"]


def test_r13_a_body_is_stored_once_redacted_and_enqueued(hooks: FlaskClient, db: Engine) -> None:
    document = _document(_status("wamid.X", "delivered"), text_message=True)
    first, body = _post(hooks, document)
    again, _ = _post(hooks, document)  # Meta redelivers
    assert (first, again) == (200, 200)
    event_id = _event_id(db, body)
    assert _count(db, "SELECT count(*) FROM webhook_events WHERE id = :i", i=event_id) == 1
    assert (
        _count(
            db,
            "SELECT count(*) FROM jobs WHERE dedupe_key = :k",
            k=f"process_webhook_event:{event_id}",
        )
        == 1
    )
    with db.connect() as conn:
        stored = json.dumps(
            conn.execute(
                text("SELECT payload FROM webhook_events WHERE id = :i"), {"i": event_id}
            ).scalar_one()
        )
    for secret in ("SENTINEL-inbound-text", "Sample Person", "919111111111", "15550001111"):
        assert secret not in stored  # decision 3A


def test_a_body_over_1_mb_is_refused(hooks: FlaskClient) -> None:
    resp = hooks.post(
        URL, data=b"x" * (1024 * 1024 + 1), headers={"X-Hub-Signature-256": "sha256=0"}
    )
    assert resp.status_code == 413


# --- Statuses (R13) -----------------------------------------------------------------------------


def test_fr_msg_03_statuses_move_the_message_forward_only(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    row = _sent_booking(world, db, session_factory)
    now = datetime.now(UTC)
    _, body = _post(
        hooks,
        _document(
            _status(
                row.provider_message_id,
                "delivered",
                at=now,
                message_id=row.id,
                pricing={"category": "utility"},
            ),
        ),
    )
    _process(session_factory, db, body)
    _, later = _post(
        hooks,
        _document(
            _status(row.provider_message_id, "read", at=now + timedelta(seconds=5)),
            _status(row.provider_message_id, "sent", at=now - timedelta(seconds=5)),  # late
        ),
    )
    _process(session_factory, db, later)
    [row] = _messages(db, row.idempotency_key)
    assert (row.status, row.pricing_category) == ("READ", "utility")
    assert row.delivered_at is not None and row.read_at is not None
    assert (
        _count(
            db,
            "SELECT count(*) FROM webhook_events WHERE processed_at IS NOT NULL"
            " AND error_code IS NULL AND id = :i",
            i=_event_id(db, later),
        )
        == 1
    )


def test_a_failed_status_records_the_mapped_code(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    row = _sent_booking(world, db, session_factory)
    _, body = _post(
        hooks, _document(_status(row.provider_message_id, "failed", errors=[{"code": 131026}]))
    )
    _process(session_factory, db, body)
    [row] = _messages(db, row.idempotency_key)
    assert (row.status, row.error_code) == ("FAILED", "MSG_RECIPIENT_INVALID")


def test_a_status_before_its_message_is_retried_then_recorded_unmatched(
    hooks: FlaskClient, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, body = _post(hooks, _document(_status("wamid.NOBODY", "delivered")))
    with pytest.raises(JobFailure) as failure:
        _process(session_factory, db, body)
    assert failure.value.code == WH_UNMATCHED and failure.value.retryable
    assert (
        _count(
            db,
            "SELECT count(*) FROM webhook_events WHERE id = :i AND processed_at IS NULL",
            i=_event_id(db, body),
        )
        == 1
    )
    _process(session_factory, db, body, attempts=5, max_attempts=5)  # the last attempt
    assert (
        _count(
            db,
            "SELECT count(*) FROM webhook_events WHERE id = :i AND error_code = :c",
            i=_event_id(db, body),
            c=WH_UNMATCHED,
        )
        == 1
    )


def test_decision_4a_a_status_settles_an_unknown_outcome_and_the_prescription_link(
    hooks: FlaskClient, world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, rx = _issued_with_consent(world)
    key = f"rx_link:{rx['id']}"
    rig = _rig(session_factory)
    rig.provider.script = [_raise(Crash())]  # accepted by Meta, then the worker died
    with pytest.raises(Crash):
        rig.rx_link(_job(db, key))
    with pytest.raises(JobFailure):
        rig.rx_link(_job(db, key, attempts=2))
    [row] = _messages(db, key)
    assert (row.status, row.error_code, row.provider_message_id) == (
        "FAILED",
        MSG_OUTCOME_UNKNOWN,
        None,
    )
    assert _link_delivery(db, rx["id"]) == "PENDING"
    assert rig.provider.calls[0].message_id == row.id  # what Meta echoes back

    _, body = _post(hooks, _document(_status("wamid.LATE", "delivered", message_id=row.id)))
    _process(session_factory, db, body)
    [row] = _messages(db, key)
    assert (row.status, row.error_code, row.provider_message_id) == (
        "DELIVERED",
        None,
        "wamid.LATE",
    )
    assert _link_delivery(db, rx["id"]) == "SENT"


# --- Reconciliation (R15 for WhatsApp) ----------------------------------------------------------


def test_r15_reconciliation_requeues_a_stuck_event_and_counts_unconfirmed(
    hooks: FlaskClient,
    world: World,
    db: Engine,
    session_factory: sessionmaker[Session],
    json_logs: LogReader,
) -> None:
    row = _sent_booking(world, db, session_factory)
    _, body = _post(hooks, _document(_status(row.provider_message_id, "delivered")))
    event_id = _event_id(db, body)
    with db.begin() as conn:  # the processing job was lost, and the message was sent long ago
        conn.execute(
            text("DELETE FROM jobs WHERE dedupe_key = :k"),
            {"k": f"process_webhook_event:{event_id}"},
        )
        conn.execute(
            text(
                "UPDATE webhook_events SET received_at = now() - interval '20 minutes'"
                " WHERE id = :i"
            ),
            {"i": event_id},
        )
    later = FakeClock(datetime.now(UTC) + timedelta(hours=25))
    reconcile = ReconcileMessages(
        uow=SqlAlchemyUnitOfWork(session_factory), clock=later, ids=Uuid7Generator()
    )
    reconcile(_job_like(event_id))
    assert (
        _count(
            db,
            "SELECT count(*) FROM jobs WHERE kind = 'process_webhook_event'"
            " AND payload->>'event_id' = :i AND state = 'queued'",
            i=str(event_id),
        )
        == 1
    )
    [report] = [e for e in json_logs() if e["event"] == "messages.reconciled"]
    assert report["webhook_events_requeued"] >= 1 and report["unconfirmed_24h"] >= 1


def _job_like(event_id: UUID) -> Any:
    from mediease_api.domain.jobs.job import ClaimedJob

    return ClaimedJob(
        id=event_id,
        kind="reconcile_messages",
        clinic_id=None,
        payload={},
        attempts=1,
        max_attempts=5,
        request_id="req-reconcile",
        locked_by="test",
    )
