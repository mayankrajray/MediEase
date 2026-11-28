"""Patient data requests on PostgreSQL (M9-P3; RUNBOOK §12, §43).

The bundled demo clinic (invented data) is imported beside the test world's clinics. Support
exports one patient's record as an encrypted zip, and erases another: the personal details go, the
clinical record stays under the code, nothing of another patient or clinic changes, and both are
in the clinic's audit log.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import pyzipper
from sqlalchemy import Engine, create_engine, text

from mediease_api.adapters.db.patient_data import ERASED_NAME, ERASED_PHONE
from mediease_api.delivery.cli import import_clinic, patient_data
from tests.conftest import TEST_IP_SALT, TEST_SIGNING_KEY, SetEnv, World

DEMO = "kesar-bagh-family-clinic"
# Invented demo patients: one with history and nothing booked, one booked tomorrow.
QUIET, BOOKED = "Rakesh Gupta", "Neha Kapoor"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def blobs(tmp_path: Path) -> Path:
    path = tmp_path / "blobs"
    path.mkdir()
    return path


@pytest.fixture
def demo(world: World, set_env: SetEnv, migrated_database_url: str, blobs: Path) -> World:
    set_env(
        {
            "APP_ENV": "local",
            "DATABASE_URL": migrated_database_url,
            "JWT_SIGNING_KEY": TEST_SIGNING_KEY,
            "AUDIT_IP_SALT": TEST_IP_SALT,
            "BLOB_STORAGE": "local",
            "BLOB_LOCAL_DIR": str(blobs),
        }
    )
    assert import_clinic.main(["--demo", "--password", "data-request-test-pw"]) == 0
    return world


def _one(db: Engine, sql: str, **params: object) -> object:
    with db.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _patient(db: Engine, name: str) -> tuple[str, str, str]:
    with db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT p.id, p.code, p.phone_e164 FROM patients p JOIN clinics c"
                " ON c.id = p.clinic_id WHERE c.slug = :slug AND p.full_name = :name"
            ),
            {"slug": DEMO, "name": name},
        ).one()
    return str(row.id), row.code, row.phone_e164


def _audit(db: Engine, action: str, patient_id: str) -> dict[str, str]:
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT actor_type, metadata FROM audit_events WHERE action = :a AND entity_id = :p"
            ),
            {"a": action, "p": patient_id},
        ).all()
    assert len(rows) == 1
    assert rows[0].actor_type == "SYSTEM"
    return dict(rows[0].metadata)


def test_m9_p3_an_export_is_an_encrypted_zip_of_the_whole_record(
    demo: World, db: Engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patient_id, code, phone = _patient(db, QUIET)
    assert patient_data.main(["export", DEMO, code.lower()], out_dir=tmp_path) == 0
    out = capsys.readouterr().out
    password = re.search(r"password \(shown once.*\): (\S+)", out)
    assert password is not None
    [archive] = list(tmp_path.glob(f"{DEMO}-{code.lower()}-*.zip"))
    assert archive.stat().st_mode & 0o777 == 0o600

    with pyzipper.AESZipFile(archive) as opened:
        with pytest.raises(RuntimeError):  # encrypted: unreadable without the password
            opened.read("record.json")
        opened.setpassword(password.group(1).encode())
        record = json.loads(opened.read("record.json"))
        assert "README.txt" in opened.namelist()

    tables = record["tables"]
    assert record["patient_code"] == code
    assert (
        tables["patient"][0]["full_name"] == QUIET and tables["patient"][0]["phone_e164"] == phone
    )
    assert len(tables["visits"]) == 2 and tables["prescriptions"] and tables["prescription_items"]
    assert tables["bills"] and tables["bill_lines"] and tables["appointments"]
    assert all("to_phone_encrypted" not in m for m in tables["messages"])
    assert all("token_hash" not in i for i in tables["patient_portal_invites"])
    assert all(v["patient_id"] == patient_id for v in tables["visits"])

    metadata = _audit(db, "patient.data_exported", patient_id)
    assert metadata["code"] == code and int(metadata["rows"]) > 5
    # Neither the name nor the phone is logged or audited; the code and counts only.
    assert QUIET not in out and phone not in out and QUIET not in json.dumps(metadata)

    # Never overwrites: the same day's export again is refused.
    assert patient_data.main(["export", DEMO, code], out_dir=tmp_path) == 2


def test_m9_p3_erasure_keeps_the_clinical_record_and_removes_who_the_patient_is(
    demo: World, db: Engine, blobs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    patient_id, code, phone = _patient(db, QUIET)
    other_id, _, other_phone = _patient(db, BOOKED)
    visits = _one(db, "SELECT count(*) FROM visits WHERE patient_id = :p", p=patient_id)
    issued = _one(db, "SELECT count(*) FROM prescriptions WHERE patient_id = :p", p=patient_id)
    # A stored prescription PDF and receipt, as the clinic's downloads would leave them.
    clinic_id = str(_one(db, "SELECT clinic_id FROM patients WHERE id = :p", p=patient_id))
    rx_id = str(
        _one(db, "SELECT id FROM prescriptions WHERE patient_id = :p LIMIT 1", p=patient_id)
    )
    bill_id = str(_one(db, "SELECT id FROM bills WHERE patient_id = :p LIMIT 1", p=patient_id))
    rx_pdf = blobs / "rx" / clinic_id / rx_id / "v1.pdf"
    receipt = blobs / "receipt" / clinic_id / bill_id / "s1.pdf"
    for file in (rx_pdf, receipt):
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"%PDF-1.7 the patient's name was here")
    with db.begin() as conn:
        conn.execute(
            text("UPDATE prescriptions SET pdf_object_key = :k WHERE id = :id"),
            {"k": f"rx/{clinic_id}/{rx_id}/v1.pdf", "id": rx_id},
        )

    assert patient_data.main(["erase", DEMO, code], ask=lambda _: code) == 0
    out = capsys.readouterr().out
    assert f"erased {code}" in out and QUIET not in out

    with db.connect() as conn:
        row = conn.execute(text("SELECT * FROM patients WHERE id = :p"), {"p": patient_id}).one()
    assert (row.full_name, row.phone_e164, row.date_of_birth) == (ERASED_NAME, ERASED_PHONE, None)
    assert row.age_years_at_registration is not None  # the age stays for the clinical record
    assert row.guardian_name is None and not row.whatsapp_consent and row.opted_out_at is not None
    assert row.code == code

    # The clinical record stays; the clinic still has every visit and prescription.
    assert _one(db, "SELECT count(*) FROM visits WHERE patient_id = :p", p=patient_id) == visits
    assert (
        _one(db, "SELECT count(*) FROM prescriptions WHERE patient_id = :p", p=patient_id) == issued
    )
    # Who the patient was is nowhere in the clinic's rows.
    assert _one(db, "SELECT count(*) FROM patients WHERE full_name = :n", n=QUIET) == 0
    for sql in (
        "SELECT count(*) FROM booking_requests WHERE contact_phone = :phone",
        "SELECT count(*) FROM notifications WHERE strpos(title, split_part(:name, ' ', 1)) > 0"
        " AND strpos(title, :code) > 0",
    ):
        assert _one(db, sql, name=QUIET, phone=phone, code=code) == 0
    # A family member who shares the phone keeps it: it is also hers (patients D1).
    assert (
        _one(
            db,
            "SELECT count(*) FROM patients WHERE phone_e164 = :phone AND full_name = :sister",
            phone=phone,
            sister="Anjali Gupta",
        )
        == 1
    )
    assert (
        _one(
            db,
            "SELECT count(*) FROM messages WHERE patient_id = :p AND to_phone_encrypted <> ''",
            p=patient_id,
        )
        == 0
    )
    assert (
        _one(
            db,
            "SELECT count(*) FROM reminders WHERE patient_id = :p AND status = 'SCHEDULED'",
            p=patient_id,
        )
        == 0
    )
    assert not rx_pdf.exists() and not receipt.exists()  # drawn again, anonymised, if downloaded

    # Another patient of the clinic, and the other clinics, are untouched.
    assert _one(db, "SELECT full_name FROM patients WHERE id = :p", p=other_id) == BOOKED
    assert _one(db, "SELECT phone_e164 FROM patients WHERE id = :p", p=other_id) == other_phone
    assert _one(db, "SELECT count(*) FROM patients WHERE full_name = :n", n=ERASED_NAME) == 1

    metadata = _audit(db, "patient.erased", patient_id)
    assert metadata["code"] == code and metadata["patient"] == "1"
    assert QUIET not in json.dumps(metadata)

    # Once only.
    assert patient_data.main(["erase", DEMO, code], ask=lambda _: code) == 1
    assert "already been erased" in capsys.readouterr().err


def test_m9_p3_erasure_waits_for_upcoming_appointments_and_needs_the_code_typed(
    demo: World, db: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    booked_id, booked_code, _ = _patient(db, BOOKED)
    assert patient_data.main(["erase", DEMO, booked_code], ask=lambda _: booked_code) == 1
    assert "upcoming appointment" in capsys.readouterr().err
    assert _one(db, "SELECT full_name FROM patients WHERE id = :p", p=booked_id) == BOOKED

    quiet_id, quiet_code, _ = _patient(db, QUIET)
    assert patient_data.main(["erase", DEMO, quiet_code], ask=lambda _: "KB-9999") == 2
    assert "not confirmed" in capsys.readouterr().err
    assert _one(db, "SELECT full_name FROM patients WHERE id = :p", p=quiet_id) == QUIET
    with db.connect() as conn:
        assert not conn.execute(
            text("SELECT 1 FROM audit_events WHERE action = 'patient.erased'")
        ).first()


def test_m9_p3_an_unknown_patient_or_clinic_is_refused(
    demo: World, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "exports"
    out.mkdir()
    assert patient_data.main(["export", DEMO, "ZZ-0001"], out_dir=out) == 1
    assert patient_data.main(["erase", "no-such-clinic", "KB-0001"], ask=lambda _: "x") == 1
    assert capsys.readouterr().err.count("no patient with that code in that clinic") == 2
    assert list(out.iterdir()) == []
