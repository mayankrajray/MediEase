"""The real ClamAV daemon (M7b-P7; NFR-20; journey 5): EICAR is found, a clean file passes.

Runs against the compose ``clamav`` service on ``127.0.0.1:3310`` (``CLAMD_TEST_HOST`` and
``CLAMD_TEST_PORT`` override); skipped when no daemon answers, e.g. on a machine without the stack.
The EICAR test string is assembled at run time so no antivirus quarantines this file.

A bare EICAR file is not a PDF, JPEG or PNG, so the upload refuses it by type before any scan.
The upload-shaped case is a PDF carrying EICAR as an embedded file: it passes the type check and
ClamAV finds it in the stream it extracts (``eicar_pdf``).
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterator
from dataclasses import replace

import pytest
from sqlalchemy import Engine, create_engine

from mediease_api.adapters.malware.clamd import ClamdScanner
from tests.booking_helpers import verified_client
from tests.conftest import UowFactory, World, make_db_app
from tests.integration.test_clinic_applications_http import MemoryStore
from tests.integration.test_portal_http import portal_csrf
from tests.upload_helpers import UPL, process, state_of

SCANNER = ClamdScanner(
    host=os.environ.get("CLAMD_TEST_HOST", "127.0.0.1"),
    port=int(os.environ.get("CLAMD_TEST_PORT", "3310")),
    timeout_seconds=30,
)

pytestmark = pytest.mark.skipif(not SCANNER.ping(), reason="no clamd on the test host")


def eicar() -> bytes:
    parts = [r"X5O!P%@AP[4\PZX54(P^)7CC)7}$", "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!", "$H+H*"]
    return "".join(parts).encode("ascii")


def eicar_pdf(payload: bytes | None = None) -> bytes:
    """A one-page PDF with ``payload`` (EICAR by default) as an embedded file."""
    data = eicar() if payload is None else payload
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R"
        b" /Names << /EmbeddedFiles << /Names [(t.txt) 4 0 R] >> >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
        b"<< /Type /Filespec /F (t.txt) /EF << /F 5 0 R >> >>",
        b"<< /Type /EmbeddedFile /Length %d >>\nstream\n%s\nendstream" % (len(data), data),
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return out


def test_nfr_20_clamd_finds_eicar() -> None:
    result = SCANNER.scan(eicar())
    assert result.clean is False and result.signature and "Eicar" in result.signature


def test_nfr_20_clamd_finds_eicar_inside_a_pdf_and_passes_a_clean_one() -> None:
    infected = SCANNER.scan(eicar_pdf())
    assert infected.clean is False and infected.signature and "Eicar" in infected.signature
    assert SCANNER.scan(eicar_pdf(b"a clean synthetic attachment")).clean is True


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def test_journey_5_an_infected_upload_is_rejected_by_the_real_scanner_and_deleted(
    world: World, db: Engine, uow_factory: UowFactory
) -> None:
    store = MemoryStore()
    w = replace(
        world, app=make_db_app(world.app.config["SETTINGS"].DATABASE_URL, blob_storage=store)
    )
    patient = verified_client(w, "eicar.patient@example.test")
    resp = patient.post(
        UPL,
        data={"file": (io.BytesIO(eicar_pdf()), "rx.pdf")},
        content_type="multipart/form-data",
        headers=portal_csrf(patient),
    )
    assert resp.status_code == 202, resp.get_json()
    process(db, uow_factory, store, scanner=SCANNER)
    body = state_of(patient, resp.get_json()["id"])
    assert (body["state"], body["rejection_code"]) == ("REJECTED", "UPL_INFECTED")
    assert not [k for k in store.objects if k.startswith("uploads/")]
