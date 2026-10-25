"""Applying to join MediEase over HTTP (M6c-P1; spec clinic-onboarding R1-R22, AC1-AC9).

Real PostgreSQL and the real composition root; certificates in the test blob directory, or in a
fake store where a test needs one that fails. The emails are rendered by running the job handler.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.security.refresh_secrets import Sha256RefreshTokenSecrets
from mediease_api.application.onboarding.email_templates import REPLY_PROMISE
from mediease_api.application.onboarding.jobs import PurgeApplications, SendApplicationEmail
from mediease_api.domain.jobs.job import APPLICATION_EMAIL_KIND, ClaimedJob
from mediease_api.ports.email import EmailMessage
from tests.conftest import UowFactory, World, make_db_app

URL = "/api/v1/public/applications"
PDF = b"%PDF-1.4\n% synthetic certificate for tests\n"
OWNER_NAME = "Synthetic Owner Name"
OWNER_PHONE = "9000000123"
OWNER_EMAIL = "applicant.owner@example.test"
REGISTRATION = "SYN-REG-7781"


def solo_body(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": "SOLO_DOCTOR",
        "clinic_name": "Sample Applying Clinic",
        "address_line": "7 Synthetic Lane",
        "city": "Pune",
        "state": "Maharashtra",
        "pincode": "411001",
        "clinic_phone": "9000000124",
        "specialties": ["Family Medicine"],
        "owner_name": OWNER_NAME,
        "owner_phone": OWNER_PHONE,
        "owner_email": OWNER_EMAIL,
        "owner_practises": True,
        "doctors": [
            {
                "name": "Dr. Synthetic Owner",
                "qualification": "MBBS",
                "council": "Maharashtra Medical Council",
                "registration_number": REGISTRATION,
                "is_owner": True,
            }
        ],
    }
    body.update(changes)
    return body


def submit(
    client: FlaskClient, body: dict[str, Any], files: dict[int, bytes] | None = None
) -> TestResponse:
    data: dict[str, Any] = {"application": json.dumps(body)}
    for position, content in (files if files is not None else {1: PDF}).items():
        data[f"certificate_{position}"] = (io.BytesIO(content), f"cert-{position}.pdf")
    return client.post(URL, data=data, content_type="multipart/form-data")


class Capture:
    provider = "test"

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class MemoryStore:
    def __init__(self, *, fail_after: int | None = None) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_after = fail_after

    def put(self, key: str, data: bytes, *, content_type: str) -> bool:
        if self.fail_after is not None and len(self.objects) >= self.fail_after:
            raise OSError("store down")
        self.objects[key] = data
        return True

    def get(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def anon(migrated_database_url: str, uow_factory: UowFactory, store: MemoryStore) -> FlaskClient:
    return make_db_app(migrated_database_url, blob_storage=store).test_client()


def _scalar(db: Engine, sql: str, **params: object) -> Any:
    with db.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _jobs(db: Engine) -> list[Any]:
    with db.connect() as conn:
        return list(
            conn.execute(
                text("SELECT id, payload FROM jobs WHERE kind = :k ORDER BY created_at"),
                {"k": APPLICATION_EMAIL_KIND},
            )
        )


def _run_email(db: Engine, uow_factory: UowFactory, job: Any) -> list[EmailMessage]:
    mail = Capture()
    SendApplicationEmail(
        uow=uow_factory(),
        clock=SystemClock(),
        secrets=Sha256RefreshTokenSecrets(),
        email=mail,
        public_base_url="https://test.mediease.example",
    )(
        ClaimedJob(
            id=job.id,
            kind=APPLICATION_EMAIL_KIND,
            clinic_id=None,
            payload=job.payload,
            attempts=1,
            max_attempts=5,
            request_id=None,
            locked_by="test",
        )
    )
    return mail.sent


def _confirm_token(db: Engine, uow_factory: UowFactory) -> str:
    [email] = _run_email(db, uow_factory, _jobs(db)[-1])
    return email.text.split("/apply/confirm/", 1)[1].split()[0]


# --- Submitting (R1-R10, AC1, AC3, AC4) --------------------------------------------------------


def test_ac1_ac3_a_solo_doctor_applies_and_nothing_in_any_clinic_changes(
    anon: FlaskClient, db: Engine, store: MemoryStore, world: World
) -> None:
    clinics = _scalar(db, "SELECT count(*) FROM clinics")
    users = _scalar(db, "SELECT count(*) FROM users")
    resp = submit(anon, solo_body())
    assert resp.status_code == 202, resp.get_json()
    body = resp.get_json()
    assert body["reference"].startswith(f"MA-{datetime.now(UTC).year}-")
    assert body["email_masked"] == "a***@example.test"
    assert resp.headers["Cache-Control"] == "no-store"

    with db.connect() as conn:
        row = conn.execute(
            text("SELECT id, status, email_verified_at, confirm_digest FROM clinic_applications")
        ).one()
        doctor = conn.execute(
            text(
                "SELECT registration_number, certificate_key, certificate_content_type,"
                " certificate_sha256 FROM clinic_application_doctors"
            )
        ).one()
    assert (row.status, row.email_verified_at, row.confirm_digest) == ("PENDING", None, None)
    assert doctor.registration_number == REGISTRATION
    assert doctor.certificate_content_type == "application/pdf"
    assert store.objects[doctor.certificate_key] == PDF
    assert len(_jobs(db)) == 1
    # AC3 (FR-ONB-02): no clinic, user, membership or doctor.
    assert _scalar(db, "SELECT count(*) FROM clinics") == clinics
    assert _scalar(db, "SELECT count(*) FROM users") == users
    action = _scalar(
        db,
        "SELECT actor_type || ':' || action FROM audit_events"
        " WHERE clinic_id IS NULL AND action LIKE 'application.%'",
    )
    assert action == "APPLICANT:application.submitted"


def test_ac4_a_renamed_text_file_is_refused_on_its_doctor_and_nothing_is_kept(
    anon: FlaskClient, db: Engine, store: MemoryStore
) -> None:
    second = {
        "name": "Dr. Second Synthetic",
        "qualification": "MBBS",
        "council": "Delhi Medical Council",
        "registration_number": "DMC-2",
    }
    body = solo_body(kind="CLINIC", owner_practises=True)
    body["doctors"].append(second)
    resp = submit(anon, body, {1: PDF, 2: b"just text renamed .pdf"})
    assert resp.status_code == 422
    error = resp.get_json()["error"]
    assert (error["code"], error["details"]) == (
        "ONB_FILE_REJECTED",
        {"position": "2", "reason": "type"},
    )
    assert _scalar(db, "SELECT count(*) FROM clinic_applications") == 0
    assert store.objects == {}


def test_r6_field_errors_name_the_doctor_from_1(anon: FlaskClient) -> None:
    body = solo_body()
    body["doctors"][0]["council"] = "Medical Council of Atlantis"
    resp = submit(anon, body)
    assert resp.status_code == 422
    assert resp.get_json()["error"]["details"]["fields"][0]["field"] == "doctors.1.council"
    missing = solo_body()
    del missing["doctors"][0]["qualification"]
    fields = submit(anon, missing).get_json()["error"]["details"]["fields"]
    assert fields[0]["field"] == "doctors.1.qualification"
    assert submit(anon, solo_body(), {}).get_json()["error"]["details"] == {
        "position": "1",
        "reason": "missing",
    }


def test_r1_json_and_oversized_requests_are_refused(anon: FlaskClient) -> None:
    assert anon.post(URL, json=solo_body()).status_code == 415
    huge = submit(anon, solo_body(), {1: b"%PDF-" + b"0" * (31 * 1024 * 1024)})
    assert huge.status_code == 413


def test_r8_the_honeypot_answers_like_a_success_and_keeps_nothing(
    anon: FlaskClient, db: Engine, store: MemoryStore
) -> None:
    resp = submit(anon, solo_body(website="https://spam.example"))
    assert resp.status_code == 202
    assert resp.get_json()["reference"].startswith("MA-")
    assert _scalar(db, "SELECT count(*) FROM clinic_applications") == 0
    assert store.objects == {} and _jobs(db) == []


def test_r10_a_failing_store_keeps_no_rows_and_no_files(
    migrated_database_url: str, uow_factory: UowFactory, db: Engine
) -> None:
    broken = MemoryStore(fail_after=1)
    client = make_db_app(migrated_database_url, blob_storage=broken).test_client()
    body = solo_body(kind="CLINIC")
    body["doctors"].append({**body["doctors"][0], "registration_number": "X-2", "is_owner": False})
    resp = submit(client, body, {1: PDF, 2: PDF})
    assert resp.status_code == 503
    assert resp.get_json()["error"]["code"] == "ONB_UPLOAD_FAILED"
    assert broken.objects == {}
    assert _scalar(db, "SELECT count(*) FROM clinic_applications") == 0


# --- Confirming (R11-R13, AC2) -----------------------------------------------------------------


def test_ac2_the_link_confirms_once_lists_it_for_ops_and_sends_the_promise(
    anon: FlaskClient, db: Engine, uow_factory: UowFactory, world: World
) -> None:
    reference = submit(anon, solo_body()).get_json()["reference"]
    ops = world.client_for(world.ops)
    assert ops.get("/api/v1/ops/applications").get_json() == {"items": []}

    [email] = _run_email(db, uow_factory, _jobs(db)[0])
    assert email.to.value == OWNER_EMAIL and reference in email.subject
    for leak in (OWNER_PHONE, REGISTRATION):
        assert leak not in email.text
    token = email.text.split("/apply/confirm/", 1)[1].split()[0]

    confirmed = anon.post(f"{URL}/confirm", json={"token": token})
    assert confirmed.status_code == 200 and confirmed.get_json() == {"reference": reference}
    again = anon.post(f"{URL}/confirm", json={"token": token})
    assert (again.status_code, again.get_json()["error"]["code"]) == (404, "ONB_CONFIRM_INVALID")
    unknown = anon.post(f"{URL}/confirm", json={"token": "not-a-real-token"})
    assert unknown.get_json()["error"]["code"] == "ONB_CONFIRM_INVALID"

    [item] = ops.get("/api/v1/ops/applications").get_json()["items"]
    assert item["reference"] == reference and item["doctors"] == 1
    assert item["possible_duplicate"] is False
    for leak in (OWNER_PHONE, OWNER_EMAIL, REGISTRATION, OWNER_NAME):
        assert leak not in json.dumps(item)
    assert world.client_for(world.a.owner).get("/api/v1/ops/applications").status_code == 403

    # AC9 (D3): the "received" email promises a reply within 2 working days.
    [received] = _run_email(db, uow_factory, _jobs(db)[-1])
    assert REPLY_PROMISE in received.text and "2 working days" in received.text


def test_r11_an_expired_link_is_refused(
    anon: FlaskClient, db: Engine, uow_factory: UowFactory
) -> None:
    submit(anon, solo_body())
    token = _confirm_token(db, uow_factory)
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinic_applications SET submitted_at = submitted_at - interval '49 hours'")
        )
    resp = anon.post(f"{URL}/confirm", json={"token": token})
    assert resp.get_json()["error"]["code"] == "ONB_CONFIRM_INVALID"


def test_r13_a_second_unconfirmed_submission_replaces_the_first(
    anon: FlaskClient, db: Engine, uow_factory: UowFactory, store: MemoryStore
) -> None:
    submit(anon, solo_body())
    first_token = _confirm_token(db, uow_factory)
    first_keys = set(store.objects)
    submit(anon, solo_body(clinic_name="Sample Applying Clinic Two"))
    assert _scalar(db, "SELECT count(*) FROM clinic_applications") == 1
    assert first_keys.isdisjoint(store.objects)
    stale = anon.post(f"{URL}/confirm", json={"token": first_token})
    assert stale.get_json()["error"]["code"] == "ONB_CONFIRM_INVALID"


# --- Limits and duplicates (R16, R17, AC5, AC6) ------------------------------------------------


def test_ac5_a_fourth_application_from_one_phone_today_is_limited(anon: FlaskClient) -> None:
    for n in range(3):
        assert submit(anon, solo_body(owner_email=f"owner{n}@example.test")).status_code == 202
    limited = submit(anon, solo_body(owner_email="owner9@example.test"))
    assert limited.status_code == 429
    assert limited.get_json()["error"]["code"] == "ONB_RATE_LIMITED"
    assert int(limited.headers["Retry-After"]) > 0


def test_ac6_a_registration_already_applied_is_flagged_and_answered_alike(
    anon: FlaskClient, db: Engine, uow_factory: UowFactory, world: World
) -> None:
    first = submit(anon, solo_body()).get_json()["reference"]
    anon.post(f"{URL}/confirm", json={"token": _confirm_token(db, uow_factory)})
    second = submit(
        anon, solo_body(owner_email="other.owner@example.test", owner_phone="9000000125")
    )
    assert second.status_code == 202 and set(second.get_json()) == {"reference", "email_masked"}
    flags = _scalar(
        db,
        "SELECT duplicate_of FROM clinic_applications WHERE reference = :r",
        r=second.get_json()["reference"],
    )
    assert flags == [first]

    # An existing clinic's doctor with the same number (typed with a space) is flagged by clinic.
    with db.begin() as conn:
        conn.execute(
            text("UPDATE doctors SET registration_number = :n WHERE id = :id"),
            {"n": "syn-reg -7781", "id": world.a.doctor.id},
        )
    third = submit(anon, solo_body(owner_email="third@example.test", owner_phone="9000000126"))
    flags = _scalar(
        db,
        "SELECT duplicate_of FROM clinic_applications WHERE reference = :r",
        r=third.get_json()["reference"],
    )
    assert f"clinic:{world.a.clinic.id}" in flags


# --- Retention and privacy (R14, R19, R20, AC7, AC8) -------------------------------------------


def test_ac7_the_purge_deletes_unconfirmed_applications_and_their_files(
    anon: FlaskClient, db: Engine, uow_factory: UowFactory, store: MemoryStore
) -> None:
    submit(anon, solo_body())
    submit(anon, solo_body(owner_email="kept@example.test", owner_phone="9000000127"))
    anon.post(f"{URL}/confirm", json={"token": _confirm_token(db, uow_factory)})
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinic_applications SET submitted_at = submitted_at - interval '73 hours'")
        )
    removed = PurgeApplications(uow=uow_factory(), clock=SystemClock(), storage=store).execute()
    assert removed == 1
    assert _scalar(db, "SELECT owner_email FROM clinic_applications") == "kept@example.test"
    assert len(store.objects) == 1


def test_ac8_logs_and_audit_carry_no_personal_detail(
    anon: FlaskClient, db: Engine, uow_factory: UowFactory, json_logs: Any
) -> None:
    submit(anon, solo_body())
    anon.post(f"{URL}/confirm", json={"token": _confirm_token(db, uow_factory)})
    logs = json.dumps(json_logs())
    with db.connect() as conn:
        audit = json.dumps(
            [dict(r._mapping) for r in conn.execute(text("SELECT metadata FROM audit_events"))],
            default=str,
        )
    for leak in (OWNER_NAME, OWNER_PHONE, "+919000000123", OWNER_EMAIL, REGISTRATION, "cert-1.pdf"):
        assert leak not in logs
        assert leak not in audit
    assert "application.submitted" in logs and "application.email_verified" in logs


def test_r16_confirming_is_limited_per_address(anon: FlaskClient) -> None:
    answers = [anon.post(f"{URL}/confirm", json={"token": f"t{n}"}).status_code for n in range(21)]
    assert answers[:20] == [404] * 20 and answers[20] == 429


def test_r12_a_confirmed_application_is_never_sent_a_new_link(
    anon: FlaskClient, db: Engine, uow_factory: UowFactory
) -> None:
    submit(anon, solo_body())
    confirm_job = _jobs(db)[0]
    anon.post(f"{URL}/confirm", json={"token": _confirm_token(db, uow_factory)})
    assert _run_email(db, uow_factory, confirm_job) == []
    application_id = UUID(str(confirm_job.payload["application_id"]))
    assert _scalar(
        db,
        "SELECT confirm_digest IS NULL FROM clinic_applications WHERE id = :i",
        i=application_id,
    )
    assert datetime.now(UTC) - _scalar(
        db, "SELECT email_verified_at FROM clinic_applications"
    ) < timedelta(minutes=5)
