"""Verified prescription uploads over HTTP (M7b; FR-UPL-01..05, NFR-20; spec prescription-uploads).

Real PostgreSQL, real layout-3 PDFs and the real identifier reader (pdfium, zxing-cpp); the
malware scanner is a fake here (the live clamd is ``test_clamd_live.py``). The upload job is run
in-process (``upload_helpers.process``) with the same in-memory blob store the app wrote to.
Synthetic people and data only.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from PIL import Image
from sqlalchemy import Engine, create_engine, text

from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.uploads.checks import ScanResult
from tests.assistant_helpers import ScriptedLlm, call, patient_turn, say, user
from tests.booking_helpers import verified_client
from tests.conftest import UowFactory, World, make_db_app
from tests.integration.test_clinic_applications_http import MemoryStore
from tests.integration.test_patient_links_http import _last4, _link, _wrong
from tests.integration.test_prescriptions_http import SAMPLE_ITEM, _fill, _issued
from tests.integration.test_visits_http import _send
from tests.portal_helpers import PORTAL, link_by_invite, portal_client
from tests.upload_helpers import (
    SENTINEL,
    UNAVAILABLE,
    UPL,
    FakeScanner,
    FixedReader,
    by_code,
    challenge,
    edited_pdf,
    photo_of,
    process,
    select,
    state_of,
    sweep,
    upload,
    withdraw,
)

OWNER_EMAIL = "uploads.patient@example.test"
REP_EMAIL = "uploads.representative@example.test"
OTHER_EMAIL = "uploads.other@example.test"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def llm() -> ScriptedLlm:
    return ScriptedLlm()


@pytest.fixture
def w(world: World, store: MemoryStore) -> World:
    """The world on an app writing to ``store`` (the console model answers)."""
    url = world.app.config["SETTINGS"].DATABASE_URL
    return replace(world, app=make_db_app(url, blob_storage=store))


def _scripted(world: World, store: MemoryStore, llm: ScriptedLlm) -> World:
    url = world.app.config["SETTINGS"].DATABASE_URL
    return replace(world, app=make_db_app(url, blob_storage=store, llm=llm))


def _held(store: MemoryStore) -> list[str]:
    """The upload files still stored (issued PDFs are cached under ``rx/`` beside them)."""
    return sorted(k for k in store.objects if k.startswith("uploads/"))


def _code(resp: Any) -> tuple[int, str]:
    return resp.status_code, str(resp.get_json()["error"]["code"])


def _pdf(world: World, rx_id: str) -> bytes:
    doctor = world.client_for(world.a.doctor_user)
    resp = doctor.get(f"/api/v1/prescriptions/{rx_id}/pdf")
    assert resp.status_code == 200 and resp.data.startswith(b"%PDF-")
    return bytes(resp.data)


def _linked(world: World, email: str = OWNER_EMAIL) -> tuple[FlaskClient, dict[str, Any], str]:
    """An issued Syrup X prescription, an account linked to its patient, the patient's ID."""
    _, visit, rx = _issued(world)
    patient = portal_client(world, email)
    link_by_invite(world.client_for(world.a.owner), patient, visit["patient_id"])
    return patient, rx, str(visit["patient_id"])


def _uploaded(client: FlaskClient, data: bytes, name: str = "rx.pdf") -> str:
    resp = upload(client, data, name)
    assert resp.status_code == 202, resp.get_json()
    body = resp.get_json()
    assert body["state"] == "QUARANTINED" and body["verification"] is None
    return str(body["id"])


def _rows(db: Engine) -> list[dict[str, Any]]:
    with db.connect() as conn:
        return [
            dict(r._mapping)
            for r in conn.execute(text("SELECT * FROM prescription_uploads ORDER BY created_at"))
        ]


def _explain(client: FlaskClient, upload_id: str) -> Any:
    return patient_turn(client, user("Explain my prescription"), context={"upload_id": upload_id})


# --- Own records: upload, scan, read, verify, delete (R1-R10, R17; FR-UPL-01..04) -----------------


def test_fr_upl_01_04_an_own_pdf_is_verified_from_the_database_and_its_file_deleted(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rx, _ = _linked(w)
    pdf = _pdf(w, rx["id"])
    upload_id = _uploaded(patient, pdf)
    assert len(_held(store)) == 1  # held in quarantine only
    (key,) = _held(store)
    assert key.startswith("uploads/") and key.endswith(upload_id)

    scanner = FakeScanner()
    process(db, uow_factory, store, scanner=scanner)
    assert scanner.scanned == [pdf]  # scanned before anything read it
    assert _held(store) == []  # R17: deleted as it left extraction

    body = state_of(patient, upload_id)
    assert body["state"] == "VERIFIED" and body["rejection_code"] is None
    v = body["verification"]
    assert (v["access"], v["version"], v["superseded"], v["selected"]) == (
        "OWN",
        1,
        False,
        "UPLOADED",
    )
    assert v["clinic_name"] == w.a.clinic.name
    assert "Syrup X" not in str(body)  # the upload view never carries the prescription's content
    (row,) = _rows(db)
    assert row["quarantine_key"] is None and str(row["prescription_id"]) == rx["id"]

    reply = _explain(patient, upload_id).get_json()["reply"]
    assert "Syrup X" in reply and "5 ml" in reply


def test_fr_upl_03_a_photo_of_the_page_is_read_by_its_qr(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rx, _ = _linked(w)
    photo = photo_of(_pdf(w, rx["id"]), scribble=None)
    upload_id = _uploaded(patient, photo, "photo.png")
    process(db, uow_factory, store)
    assert state_of(patient, upload_id)["state"] == "VERIFIED"


def test_r9_the_typed_code_verifies_at_once_in_any_accepted_form(w: World, db: Engine) -> None:
    patient, rx, _ = _linked(w)
    code = rx["id"]
    for typed in (code, code.upper(), code.replace("-", ""), f"MEDIEASE-RX:1:{code}"):
        resp = by_code(patient, typed)
        assert resp.status_code == 201, resp.get_json()
        assert resp.get_json()["state"] == "VERIFIED"
        assert resp.get_json()["source"] == "CODE"
    bad = by_code(patient, "not-a-code")
    assert _code(bad) == (422, "REQ_VALIDATION_FAILED")


# --- The mandatory boundary (R8, R16; ADR-0023): an edited document changes nothing -------------


@pytest.mark.parametrize("kind", ["pdf", "photo"])
def test_nfr_20_an_edited_document_with_a_genuine_qr_gives_the_model_only_the_database_record(
    world: World,
    store: MemoryStore,
    llm: ScriptedLlm,
    db: Engine,
    uow_factory: UowFactory,
    kind: str,
) -> None:
    w = _scripted(world, store, llm)
    patient, rx, _ = _linked(w)
    forged = edited_pdf(uow_factory, w.a.clinic.id, UUID(rx["id"]))
    data = forged if kind == "pdf" else photo_of(_pdf(w, rx["id"]))
    if kind == "pdf":  # the forgery really does carry the edited text in its text layer
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(forged)
        try:
            layer = doc[0].get_textpage().get_text_range()
        finally:
            doc.close()
        assert SENTINEL in layer and rx["id"] in layer

    upload_id = _uploaded(patient, data, "forged.pdf" if kind == "pdf" else "forged.png")
    process(db, uow_factory, store)
    assert state_of(patient, upload_id)["state"] == "VERIFIED"
    assert _held(store) == []

    llm.steps = [call("explain_prescription"), say("Take 5 ml of Syrup X, 5 days.")]
    resp = _explain(patient, upload_id)
    assert resp.status_code == 200, resp.get_json()
    seen = llm.seen_text()
    assert "Syrup X" in seen and "5 ml" in seen  # the database's lines
    assert SENTINEL not in seen and "900 mg" not in seen and "90 days" not in seen
    assert SENTINEL not in resp.get_json()["reply"]


# --- Rejections, each with the file deleted (R1, R5-R7, AC: journey 5) ---------------------------


def test_nfr_20_an_infected_file_is_rejected_and_deleted_unread(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rx, _ = _linked(w)
    upload_id = _uploaded(patient, _pdf(w, rx["id"]))
    reader = FixedReader([UUID(rx["id"])])
    process(
        db,
        uow_factory,
        store,
        scanner=FakeScanner(ScanResult(clean=False, signature="Eicar-Test-Signature")),
        reader=reader,
    )
    body = state_of(patient, upload_id)
    assert (body["state"], body["rejection_code"]) == ("REJECTED", "UPL_INFECTED")
    assert _held(store) == []
    assert _code(_explain(patient, upload_id)) == (409, "UPL_NOT_VERIFIED")


def test_r5_an_unreachable_scanner_is_retried_and_finally_rejects_never_skips(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rx, _ = _linked(w)
    upload_id = _uploaded(patient, _pdf(w, rx["id"]))
    down = FakeScanner(UNAVAILABLE)
    with pytest.raises(JobFailure) as failed:
        process(db, uow_factory, store, scanner=down, attempts=1, keep=True)
    assert failed.value.code == "UPL_SCAN_UNAVAILABLE" and failed.value.retryable
    assert state_of(patient, upload_id)["state"] == "SCANNING"
    assert len(_held(store)) == 1  # kept for the retry

    process(db, uow_factory, store, scanner=down, attempts=4, max_attempts=4)
    body = state_of(patient, upload_id)
    assert (body["state"], body["rejection_code"]) == ("REJECTED", "UPL_SCAN_UNAVAILABLE")
    assert _held(store) == []


@pytest.mark.parametrize(
    ("data", "name", "code"),
    [
        (None, "blank.png", "UPL_NO_IDENTIFIER"),
        (b"%PDF-1.7\nthis is not really a pdf", "broken.pdf", "UPL_UNREADABLE"),
        (b"\x89PNG\r\n\x1a\n" + b"0" * 64, "broken.png", "UPL_UNREADABLE"),
    ],
)
def test_r6_r7_files_without_a_readable_identifier_are_rejected(
    w: World,
    store: MemoryStore,
    db: Engine,
    uow_factory: UowFactory,
    data: bytes | None,
    name: str,
    code: str,
) -> None:
    patient = verified_client(w, OWNER_EMAIL)
    if data is None:
        image = Image.new("RGB", (600, 800), "white")
        out = io.BytesIO()
        image.save(out, format="PNG")
        data = out.getvalue()
    upload_id = _uploaded(patient, data, name)
    process(db, uow_factory, store)
    body = state_of(patient, upload_id)
    assert (body["state"], body["rejection_code"]) == ("REJECTED", code)
    assert _held(store) == []


def test_r7_two_different_identifiers_are_ambiguous(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rx, _ = _linked(w)
    upload_id = _uploaded(patient, _pdf(w, rx["id"]))
    process(db, uow_factory, store, reader=FixedReader([UUID(rx["id"]), UUID(int=7)]))
    assert state_of(patient, upload_id)["rejection_code"] == "UPL_AMBIGUOUS"


def test_r1_type_size_and_framing_are_refused_before_anything_is_stored(
    w: World, store: MemoryStore
) -> None:
    patient = portal_client(w, OWNER_EMAIL)
    assert _code(upload(patient, b"GIF89a" + b"0" * 64, "x.gif")) == (422, "UPL_FILE_REJECTED")
    assert _code(upload(patient, b"", "empty.pdf")) == (422, "UPL_FILE_REJECTED")
    big = upload(patient, b"%PDF-" + b"0" * (10 * 1024 * 1024 + 70 * 1024), "big.pdf")
    assert big.status_code == 413
    from tests.integration.test_portal_http import portal_csrf

    plain = patient.post(UPL, data=b"%PDF-1.7", headers={**portal_csrf(patient)})
    assert plain.status_code == 415
    assert _held(store) == []


def test_r2_three_in_flight_and_an_hourly_limit(w: World, store: MemoryStore) -> None:
    patient, rx, _ = _linked(w)
    pdf = b"%PDF-1.7\n%synthetic\n" + b"0" * 64
    for _ in range(3):
        _uploaded(patient, pdf)
    assert _code(upload(patient, pdf)) == (409, "UPL_TOO_MANY")
    for _ in range(6):  # 4 file uploads counted so far, 10 per hour
        assert by_code(patient, rx["id"]).status_code == 201
    limited = by_code(patient, rx["id"])
    assert _code(limited) == (429, "UPL_RATE_LIMITED")
    assert int(limited.headers["Retry-After"]) >= 1


# --- Someone else's prescription: the last-4 check (R11-R14; D7) ---------------------------------


def test_fr_upl_04_a_representative_passes_the_check_and_gets_that_prescription_only(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    _, visit, rx = _issued(w)
    _link(w, rx["id"])  # the prescription's link, as the clinic sends it
    right = _last4(w, visit["patient_id"])
    rep = verified_client(w, REP_EMAIL)
    upload_id = _uploaded(rep, _pdf(w, rx["id"]))
    process(db, uow_factory, store)
    waiting = state_of(rep, upload_id)
    assert (waiting["state"], waiting["attempts_left"], waiting["verification"]) == (
        "NEEDS_CHALLENGE",
        5,
        None,
    )
    assert _held(store) == []  # the file is gone before the check is even asked

    wrong = challenge(rep, upload_id, _wrong(right))
    assert _code(wrong) == (401, "UPL_CHALLENGE_FAILED")
    assert wrong.get_json()["error"]["details"]["attempts_left"] == "4"

    passed = challenge(rep, upload_id, right)
    assert passed.status_code == 200, passed.get_json()
    v = passed.get_json()["verification"]
    assert (v["access"], v["selected"]) == ("REPRESENTATIVE", "UPLOADED")

    reply = _explain(rep, upload_id).get_json()["reply"]
    assert "Syrup X" in reply
    # No portal link was made: the representative's own records stay empty (R14).
    assert rep.get(f"{PORTAL}/links").get_json()["items"] == []
    assert rep.get(f"{PORTAL}/prescriptions").get_json()["items"] == []


def test_r12_an_unknown_code_and_a_real_one_answer_the_same_way(w: World) -> None:
    _, visit, rx = _issued(w)
    _link(w, rx["id"])
    rep = verified_client(w, REP_EMAIL)
    real = by_code(rep, rx["id"]).get_json()
    made_up = by_code(rep, str(UUID(int=12345))).get_json()
    for body in (real, made_up):
        assert (body["state"], body["attempts_left"], body["verification"]) == (
            "NEEDS_CHALLENGE",
            5,
            None,
        )
    answers = [
        challenge(rep, body["id"], _wrong(_last4(w, visit["patient_id"])))
        for body in (real, made_up)
    ]
    assert [_code(a) for a in answers] == [(401, "UPL_CHALLENGE_FAILED")] * 2
    assert answers[0].get_json()["error"]["message"] == answers[1].get_json()["error"]["message"]
    assert [a.get_json()["error"]["details"] for a in answers] == [{"attempts_left": "4"}] * 2


def test_r12_five_wrong_answers_end_the_upload(w: World) -> None:
    _, visit, rx = _issued(w)
    _link(w, rx["id"])
    rep = verified_client(w, REP_EMAIL)
    upload_id = by_code(rep, rx["id"]).get_json()["id"]
    wrong = _wrong(_last4(w, visit["patient_id"]))
    lefts = [
        challenge(rep, upload_id, wrong).get_json()["error"]["details"]["attempts_left"]
        for _ in range(5)
    ]
    assert lefts == ["4", "3", "2", "1", "0"]
    body = state_of(rep, upload_id)
    assert (body["state"], body["rejection_code"]) == ("REJECTED", "UPL_LOCKED")
    assert _code(challenge(rep, upload_id, _last4(w, visit["patient_id"]))) == (
        409,
        "UPL_NOT_AWAITING",
    )


def test_r11_an_unverified_account_cannot_answer_the_check(w: World) -> None:
    _, _, rx = _issued(w)
    rep = portal_client(w, REP_EMAIL)
    upload_id = by_code(rep, rx["id"]).get_json()["id"]
    assert _code(challenge(rep, upload_id, "0000")) == (403, "PRT_UNVERIFIED_ACCOUNT")


def test_journey_4_another_accounts_upload_is_not_found(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rx, _ = _linked(w)
    upload_id = by_code(patient, rx["id"]).get_json()["id"]
    other = verified_client(w, OTHER_EMAIL)
    assert other.get(f"{UPL}/{upload_id}").status_code == 404
    assert _code(_explain(other, upload_id)) == (404, "REQ_NOT_FOUND")
    assert _code(select(other, upload_id, "LATEST")) == (404, "REQ_NOT_FOUND")
    assert withdraw(other, upload_id).status_code == 404
    assert state_of(patient, upload_id)["state"] == "VERIFIED"


# --- Superseded versions: never silently replaced (R15, R16; D3; journey 3) ----------------------


def _revised(world: World, rx: dict[str, Any]) -> dict[str, Any]:
    doctor = world.client_for(world.a.doctor_user)
    v2 = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise").get_json()
    _fill(doctor, v2, items=[{**SAMPLE_ITEM, "dose": "2.5 ml"}])
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{v2['id']}/issue", {"revision": 2})
    assert issued.status_code == 200, issued.get_json()
    body: dict[str, Any] = issued.get_json()
    return body


def test_fr_upl_05_a_superseded_upload_waits_for_the_users_choice_and_the_ai_follows_it(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, v1, _ = _linked(w)
    old_pdf = _pdf(w, v1["id"])
    _revised(w, v1)
    upload_id = _uploaded(patient, old_pdf)
    process(db, uow_factory, store)
    body = state_of(patient, upload_id)
    v = body["verification"]
    assert (v["version"], v["superseded"], v["latest_version"], v["selected"]) == (
        1,
        True,
        2,
        None,
    )
    # Nothing is chosen for the user.
    assert _code(_explain(patient, upload_id)) == (409, "UPL_SELECTION_REQUIRED")

    chosen = select(patient, upload_id, "UPLOADED")
    assert chosen.get_json()["verification"]["selected"] == "UPLOADED"
    historical = _explain(patient, upload_id).get_json()["reply"]
    assert "older version" in historical and "5 ml" in historical and "2.5 ml" not in historical

    latest = select(patient, upload_id, "LATEST")
    assert latest.get_json()["verification"]["selected"] == "LATEST"
    current = _explain(patient, upload_id).get_json()["reply"]
    assert "older version" not in current and "2.5 ml" in current


def test_r15_a_representative_may_choose_the_latest_of_the_same_chain(w: World, db: Engine) -> None:
    _, visit, v1 = _issued(w)
    _link(w, v1["id"])
    _revised(w, v1)
    rep = verified_client(w, REP_EMAIL)
    upload_id = by_code(rep, v1["id"]).get_json()["id"]
    passed = challenge(rep, upload_id, _last4(w, visit["patient_id"])).get_json()
    assert passed["verification"]["superseded"] is True
    select(rep, upload_id, "LATEST")
    assert "2.5 ml" in _explain(rep, upload_id).get_json()["reply"]


# --- Withdrawal, expiry and the sweep (R17, R18; D6) ---------------------------------------------


def test_r17_withdrawing_deletes_the_file_and_ends_the_grant(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rx, _ = _linked(w)
    pending = _uploaded(patient, _pdf(w, rx["id"]))
    assert withdraw(patient, pending).status_code == 204
    assert _held(store) == []
    verified = by_code(patient, rx["id"]).get_json()["id"]
    assert withdraw(patient, verified).status_code == 204
    body = state_of(patient, verified)
    assert (body["state"], body["rejection_code"], body["verification"]) == (
        "REJECTED",
        "UPL_WITHDRAWN",
        None,
    )
    assert _code(_explain(patient, verified)) == (409, "UPL_NOT_VERIFIED")
    process(db, uow_factory, store)  # the queued job finds nothing to do
    assert state_of(patient, pending)["rejection_code"] == "UPL_WITHDRAWN"


def test_r16_an_expired_grant_is_no_longer_usable(w: World, db: Engine) -> None:
    patient, rx, _ = _linked(w)
    upload_id = by_code(patient, rx["id"]).get_json()["id"]
    with db.begin() as conn:
        conn.execute(
            text("UPDATE prescription_uploads SET expires_at = now() - interval '1 minute'")
        )
    assert _code(_explain(patient, upload_id)) == (409, "UPL_NOT_VERIFIED")


def test_r18_the_sweep_ends_abandoned_uploads_and_expired_checks_and_deletes_old_rows(
    w: World, store: MemoryStore, db: Engine, uow_factory: UowFactory
) -> None:
    patient, rx, _ = _linked(w)
    abandoned = _uploaded(patient, _pdf(w, rx["id"]))
    rep = verified_client(w, REP_EMAIL)
    expired = by_code(rep, str(UUID(int=99))).get_json()["id"]
    old = by_code(patient, rx["id"]).get_json()["id"]
    fresh = _uploaded(patient, b"%PDF-1.7\n%fresh\n" + b"0" * 32)
    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE prescription_uploads SET created_at = now() - interval '2 hours',"
                " updated_at = now() - interval '2 hours' WHERE id = :i"
            ),
            {"i": abandoned},
        )
        conn.execute(
            text(
                "UPDATE prescription_uploads SET created_at = now() - interval '25 hours',"
                " updated_at = now() - interval '25 hours' WHERE id = :i"
            ),
            {"i": expired},
        )
        conn.execute(
            text(
                "UPDATE prescription_uploads SET created_at = now() - interval '31 days',"
                " verified_at = now() - interval '31 days', updated_at = now() - interval '31 days'"
                " WHERE id = :i"
            ),
            {"i": old},
        )
    sweep(uow_factory, store)
    assert state_of(patient, abandoned)["rejection_code"] == "UPL_ABANDONED"
    assert state_of(rep, expired)["rejection_code"] == "UPL_EXPIRED"
    assert patient.get(f"{UPL}/{old}").status_code == 404
    assert state_of(patient, fresh)["state"] == "QUARANTINED"
    assert _held(store) == [f"uploads/{_account(db, OWNER_EMAIL)}/{fresh}"]


def _account(db: Engine, email: str) -> str:
    with db.connect() as conn:
        return str(
            conn.execute(
                text("SELECT id FROM patient_accounts WHERE email = :e"), {"e": email}
            ).scalar_one()
        )


def test_d6_no_staff_route_serves_or_lists_an_upload(w: World) -> None:
    patient, rx, _ = _linked(w)
    upload_id = by_code(patient, rx["id"]).get_json()["id"]
    owner = w.client_for(w.a.owner)
    for url in (f"{UPL}/{upload_id}", f"/api/v1/prescription-uploads/{upload_id}"):
        assert owner.get(url).status_code in (401, 404)
    assert not any(
        "upload" in rule.rule
        for rule in w.app.url_map.iter_rules()
        if not rule.rule.startswith(UPL)
    )
