"""Booking confirmations and prescription links end to end on PostgreSQL (M5-P2).

FR-APT-06, FR-MSG-01, 02, 04; spec reminders-and-messaging R5-R8, AC4, AC7; prescriptions R14,
R15. Changes go through HTTP (so the job is enqueued by the real use case, in its transaction);
the job's handler then runs with a scripted provider, as the worker would run it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.messaging.catalog import YamlTemplateCatalog
from mediease_api.adapters.security.link_signer import HmacLinkSigner
from mediease_api.adapters.security.phone_cipher import FernetPhoneCipher
from mediease_api.application.links.use_cases import LinkTokens
from mediease_api.application.messaging.booking import SendBookingConfirmation
from mediease_api.application.messaging.rx_link import SendRxLink
from mediease_api.application.messaging.sender import MessageSender
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.messaging.errors import (
    MSG_OUTCOME_UNKNOWN,
    MSG_PROVIDER_RATE_LIMIT,
    MSG_RECIPIENT_INVALID,
    ProviderOutcomeUnknown,
    ProviderRefused,
)
from mediease_api.domain.messaging.message import Channel
from mediease_api.ports.messaging import OutboundTemplateMessage, ProviderAccepted
from tests.conftest import LogReader, World
from tests.fakes import FakeClock
from tests.integration.test_appointments_http import _patient
from tests.integration.test_prescriptions_http import SAMPLE_ITEM, _draft, _fill
from tests.integration.test_visits_http import _send
from tests.sessions_now import running_session

SENTINEL = "SENTINEL-msg-7f3a"
PUBLIC = "https://app.example.test"
# The keys the test app signs links with (conftest valid env: the development key).
LINK_KEYS = {"dev": b"change-me-local-only-patient-link-key-0001"}


class Crash(BaseException):
    """The worker process dying: not an ``Exception``, so nothing in the handler catches it."""


@dataclass
class ScriptedProvider:
    """Accepts unless told otherwise; each script entry is used once, in order."""

    script: list[Callable[[], None]] = field(default_factory=list)
    calls: list[OutboundTemplateMessage] = field(default_factory=list)

    @property
    def channel(self) -> Channel:
        return Channel.CONSOLE

    @property
    def provider(self) -> str:
        return "scripted"

    def send_template(self, msg: OutboundTemplateMessage) -> ProviderAccepted:
        self.calls.append(msg)
        if self.script:
            self.script.pop(0)()
        return ProviderAccepted(
            provider_message_id=f"scripted-{len(self.calls)}-{msg.idempotency_key}"
        )


def _raise(error: BaseException) -> Callable[[], None]:
    def go() -> None:
        raise error

    return go


@dataclass
class Rig:
    provider: ScriptedProvider
    cipher: FernetPhoneCipher
    booking: SendBookingConfirmation
    rx_link: SendRxLink


def _rig(
    session_factory: sessionmaker[Session], *, clock: Any = None, window_hours: int = 24
) -> Rig:
    provider = ScriptedProvider()
    cipher = FernetPhoneCipher([Fernet.generate_key()])
    clock = clock or SystemClock()
    ids = Uuid7Generator()
    sender = MessageSender(
        uow=SqlAlchemyUnitOfWork(session_factory),
        clock=clock,
        ids=ids,
        messaging=provider,
        templates=YamlTemplateCatalog.from_package(),
        phones=cipher,
    )
    return Rig(
        provider=provider,
        cipher=cipher,
        booking=SendBookingConfirmation(sender=sender),
        rx_link=SendRxLink(
            sender=sender,
            ids=ids,
            tokens=LinkTokens(HmacLinkSigner(LINK_KEYS)),
            public_base_url=PUBLIC,
            window=timedelta(hours=window_hours),
        ),
    )


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _job(db: Engine, key: str, *, attempts: int = 1, max_attempts: int = 5) -> ClaimedJob:
    with db.connect() as conn:
        row = conn.execute(text("SELECT * FROM jobs WHERE dedupe_key = :k"), {"k": key}).one()
    return ClaimedJob(
        id=row.id,
        kind=row.kind,
        clinic_id=row.clinic_id,
        payload=row.payload,
        attempts=attempts,
        max_attempts=max_attempts,
        request_id=row.request_id,
        locked_by="test",
        dedupe_key=row.dedupe_key,
    )


def _jobs(db: Engine, key: str) -> int:
    with db.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM jobs WHERE dedupe_key = :k"), {"k": key}
            ).scalar_one()
        )


def _messages(db: Engine, key: str) -> list[Any]:
    with db.connect() as conn:
        return list(
            conn.execute(text("SELECT * FROM messages WHERE idempotency_key = :k"), {"k": key})
        )


def _consenting_patient(desk: FlaskClient, name: str, *, whatsapp: bool = True) -> str:
    patient_id = _patient(desk, name)
    resp = _send(
        desk, "PUT", f"/api/v1/patients/{patient_id}/consent", {"whatsapp": whatsapp, "sms": False}
    )
    assert resp.status_code == 200, resp.get_json()
    return patient_id


def _booked(
    world: World, *, whatsapp: bool = True, session: dict[str, Any] | None = None
) -> tuple[FlaskClient, str]:
    """A booking in ``session`` (one running session per test: ``running_session`` once)."""
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = session or running_session(owner, world.a.doctor.id)
    patient_id = _consenting_patient(desk, "Asha Rao", whatsapp=whatsapp)
    resp = _send(
        desk,
        "POST",
        "/api/v1/appointments",
        {"session_id": session["id"], "patient_id": patient_id},
    )
    assert resp.status_code == 201, resp.get_json()
    return desk, str(resp.get_json()["id"])


def _issued_with_consent(world: World, **fill: Any) -> tuple[FlaskClient, dict[str, Any]]:
    doctor, visit, rx = _draft(world)
    desk = world.client_for(world.a.desk)
    consent = _send(
        desk,
        "PUT",
        f"/api/v1/patients/{visit['patient_id']}/consent",
        {"whatsapp": True, "sms": False},
    )
    assert consent.status_code == 200, consent.get_json()
    assert _fill(doctor, rx, **fill).status_code == 200
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    assert issued.status_code == 200, issued.get_json()
    return doctor, issued.get_json()


def _link_delivery(db: Engine, rx_id: str) -> str:
    with db.connect() as conn:
        return str(
            conn.execute(
                text("SELECT link_delivery FROM prescriptions WHERE id = :i"), {"i": rx_id}
            ).scalar_one()
        )


# --- Booking confirmations (FR-APT-06, R5, R6, R8) ----------------------------------------------


def test_fr_apt_06_a_booking_sends_one_confirmation(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, appointment_id = _booked(world)
    key = f"booking_confirmed:{appointment_id}"
    assert _jobs(db, key) == 1
    rig = _rig(session_factory)

    rig.booking(_job(db, key))

    [call] = rig.provider.calls
    assert call.template.key == "booking_confirmed"
    assert set(call.variables) == {"clinic_name", "doctor_name", "date_time_or_token"}
    assert call.variables["clinic_name"] == world.a.clinic.name
    assert call.variables["doctor_name"] == world.a.doctor.display_name
    assert "token 1" in call.variables["date_time_or_token"]
    [row] = _messages(db, key)
    assert (row.status, row.channel, row.provider, row.template_version) == (
        "SENT",
        "CONSOLE",
        "scripted",
        1,
    )
    assert (row.source_type, str(row.source_id)) == ("APPOINTMENT", appointment_id)
    assert row.sent_at is not None and row.sending_started_at is None
    # Decision 1A: the stored number is ciphertext that only the key opens.
    assert call.to.e164 not in row.to_phone_encrypted
    assert call.to.e164[-10:] not in row.to_phone_encrypted
    assert rig.cipher.decrypt(row.to_phone_encrypted) == call.to

    rig.booking(_job(db, key))  # the job again (a retry after a lost outcome write)
    assert len(rig.provider.calls) == 1
    assert len(_messages(db, key)) == 1


def test_no_job_without_consent_and_r5_consent_is_read_again_at_send_time(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    session = running_session(world.client_for(world.a.owner), world.a.doctor.id)
    _, refused = _booked(world, whatsapp=False, session=session)
    assert _jobs(db, f"booking_confirmed:{refused}") == 0

    desk, appointment_id = _booked(world, session=session)
    key = f"booking_confirmed:{appointment_id}"
    with db.connect() as conn:
        patient_id = conn.execute(
            text("SELECT patient_id FROM appointments WHERE id = :i"), {"i": appointment_id}
        ).scalar_one()
    assert _send(desk, "POST", f"/api/v1/patients/{patient_id}/opt-out").status_code == 200
    rig = _rig(session_factory)
    rig.booking(_job(db, key))
    assert rig.provider.calls == []
    assert _messages(db, key) == []


def test_a_cancelled_appointment_is_not_confirmed(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    desk, appointment_id = _booked(world)
    cancelled = _send(
        desk,
        "POST",
        f"/api/v1/appointments/{appointment_id}/cancel",
        {"reason": "PATIENT_REQUEST"},
    )
    assert cancelled.status_code == 200, cancelled.get_json()
    rig = _rig(session_factory)
    rig.booking(_job(db, f"booking_confirmed:{appointment_id}"))
    assert rig.provider.calls == []


# --- At most once (R6, R7, AC4, decision 4A) ----------------------------------------------------


def test_ac4_a_crash_after_the_provider_accepted_never_sends_twice(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, appointment_id = _booked(world)
    key = f"booking_confirmed:{appointment_id}"
    rig = _rig(session_factory)
    rig.provider.script = [_raise(Crash())]  # accepted, then the worker dies before recording it

    with pytest.raises(Crash):
        rig.booking(_job(db, key))
    [row] = _messages(db, key)
    assert row.status == "QUEUED" and row.sending_started_at is not None

    with pytest.raises(JobFailure) as failure:  # the reaped job runs again
        rig.booking(_job(db, key, attempts=2))
    assert (failure.value.code, failure.value.retryable) == (MSG_OUTCOME_UNKNOWN, False)
    assert len(rig.provider.calls) == 1
    [row] = _messages(db, key)
    assert (row.status, row.error_code) == ("FAILED", MSG_OUTCOME_UNKNOWN)


def test_r7_a_refusal_is_retried_and_a_timeout_is_not(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    session = running_session(world.client_for(world.a.owner), world.a.doctor.id)
    _, first = _booked(world, session=session)
    key = f"booking_confirmed:{first}"
    rig = _rig(session_factory)
    rig.provider.script = [_raise(ProviderRefused(MSG_PROVIDER_RATE_LIMIT))]
    with pytest.raises(JobFailure) as failure:
        rig.booking(_job(db, key))
    assert (failure.value.code, failure.value.retryable) == (MSG_PROVIDER_RATE_LIMIT, True)
    [row] = _messages(db, key)
    assert (row.status, row.error_code, row.sending_started_at) == (
        "QUEUED",
        MSG_PROVIDER_RATE_LIMIT,
        None,
    )
    rig.booking(_job(db, key, attempts=2))
    assert len(rig.provider.calls) == 2
    [row] = _messages(db, key)
    assert (row.status, row.error_code) == ("SENT", None)

    _, second = _booked(world, session=session)
    key = f"booking_confirmed:{second}"
    rig.provider.script = [_raise(ProviderOutcomeUnknown())]
    with pytest.raises(JobFailure) as failure:
        rig.booking(_job(db, key))
    assert (failure.value.code, failure.value.retryable) == (MSG_OUTCOME_UNKNOWN, False)
    assert _messages(db, key)[0].status == "FAILED"


def test_r7_a_permanent_refusal_or_the_last_attempt_fails_the_message(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    rig = _rig(session_factory)
    session = running_session(world.client_for(world.a.owner), world.a.doctor.id)
    _, first = _booked(world, session=session)
    rig.provider.script = [_raise(ProviderRefused(MSG_RECIPIENT_INVALID))]
    with pytest.raises(JobFailure) as failure:
        rig.booking(_job(db, f"booking_confirmed:{first}"))
    assert failure.value.retryable is False
    row = _messages(db, f"booking_confirmed:{first}")[0]
    assert (row.status, row.error_code) == ("FAILED", MSG_RECIPIENT_INVALID)

    _, second = _booked(world, session=session)
    rig.provider.script = [_raise(ProviderRefused(MSG_PROVIDER_RATE_LIMIT))]
    with pytest.raises(JobFailure):
        rig.booking(_job(db, f"booking_confirmed:{second}", attempts=5, max_attempts=5))
    row = _messages(db, f"booking_confirmed:{second}")[0]
    assert (row.status, row.error_code) == ("FAILED", MSG_PROVIDER_RATE_LIMIT)


# --- Prescription links (prescriptions R14, R15) ------------------------------------------------


def test_r15_a_fresh_pending_link_is_sent_once_and_marked_sent(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    doctor, rx = _issued_with_consent(world)
    key = f"rx_link:{rx['id']}"
    assert rx["link_delivery"] == "PENDING" and _jobs(db, key) == 1
    rig = _rig(session_factory)

    rig.rx_link(_job(db, key))

    [call] = rig.provider.calls
    assert call.template.key == "rx_ready"
    assert call.variables["link"].startswith(f"{PUBLIC}/p/")
    shown = _send(doctor, "GET", f"/api/v1/prescriptions/{rx['id']}/link").get_json()
    assert call.variables["link"].endswith(shown["url"].rsplit("/p/", 1)[1])
    [row] = _messages(db, key)
    assert row.variables == {"clinic_name": world.a.clinic.name, "link": "[link]"}  # decision 5A
    assert (row.source_type, str(row.source_id)) == ("PRESCRIPTION", rx["id"])
    assert _link_delivery(db, rx["id"]) == "SENT"

    revised = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise").get_json()
    assert _fill(doctor, revised).status_code == 200
    v2 = _send(doctor, "POST", f"/api/v1/prescriptions/{revised['id']}/issue", {"revision": 2})
    rig.rx_link(_job(db, f"rx_link:{v2.get_json()['id']}"))
    updated = rig.provider.calls[-1]
    assert updated.template.key == "rx_updated"
    assert updated.variables["link"] == call.variables["link"]  # one link per chain


def test_r15_a_25_hour_old_pending_link_is_expired_not_sent(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    _, rx = _issued_with_consent(world)
    later = FakeClock(datetime.now(UTC) + timedelta(hours=25))
    rig = _rig(session_factory, clock=later)

    rig.rx_link(_job(db, f"rx_link:{rx['id']}"))

    assert rig.provider.calls == []
    assert _messages(db, f"rx_link:{rx['id']}") == []
    assert _link_delivery(db, rx["id"]) == "EXPIRED"
    with db.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT actor_type, actor_user_id, metadata FROM audit_events"
                " WHERE action = 'prescription.link_expired' AND entity_id = :i"
            ),
            {"i": rx["id"]},
        ).one()
    assert (audit.actor_type, audit.actor_user_id) == ("SYSTEM", None)
    assert audit.metadata == {"version": "1", "reason": "too_old"}


def test_r15_a_superseded_version_is_never_sent(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    doctor, rx = _issued_with_consent(world)
    revised = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise").get_json()
    assert _fill(doctor, revised).status_code == 200
    v2 = _send(doctor, "POST", f"/api/v1/prescriptions/{revised['id']}/issue", {"revision": 2})
    assert v2.status_code == 200
    rig = _rig(session_factory)
    rig.rx_link(_job(db, f"rx_link:{rx['id']}"))
    assert rig.provider.calls == []
    assert _link_delivery(db, rx["id"]) == "SUPERSEDED"


# --- AC7: nothing clinical leaves (FR-MSG-04, R8) ------------------------------------------------


def test_ac7_no_message_variable_job_payload_or_log_carries_prescription_text(
    world: World,
    db: Engine,
    session_factory: sessionmaker[Session],
    json_logs: LogReader,
) -> None:
    _, rx = _issued_with_consent(
        world,
        items=[{**SAMPLE_ITEM, "medicine_name": f"Syrup {SENTINEL}", "notes": SENTINEL}],
        advice={"diet": [SENTINEL], "return_if": [SENTINEL]},
    )
    key = f"rx_link:{rx['id']}"
    job = _job(db, key)
    rig = _rig(session_factory)
    rig.rx_link(job)

    [call] = rig.provider.calls
    assert SENTINEL not in json.dumps(dict(call.variables))
    assert SENTINEL not in json.dumps(dict(job.payload))
    [row] = _messages(db, key)
    assert SENTINEL not in json.dumps(row.variables)
    logs = json.dumps(json_logs())
    assert SENTINEL not in logs
    assert call.to.e164 not in logs  # and no full phone number either
    assert call.variables["link"].rsplit("/", 1)[1] not in logs  # nor the signed link


def test_the_request_id_travels_from_the_booking_to_the_job_and_the_message(
    world: World, db: Engine, session_factory: sessionmaker[Session]
) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    session = running_session(owner, world.a.doctor.id)
    patient_id = _consenting_patient(desk, "Bina Shah")
    csrf = desk.get_cookie("me_csrf", path="/")
    assert csrf is not None
    resp = desk.post(
        "/api/v1/appointments",
        json={"session_id": session["id"], "patient_id": patient_id},
        headers={"X-CSRF-Token": csrf.value, "X-Request-ID": "req-m5p2-0001"},
    )
    assert resp.status_code == 201, resp.get_json()
    key = f"booking_confirmed:{resp.get_json()['id']}"
    job = _job(db, key)
    assert job.request_id == "req-m5p2-0001"
    _rig(session_factory).booking(job)
    assert _messages(db, key)[0].request_id == "req-m5p2-0001"
    assert isinstance(job.clinic_id, UUID)
