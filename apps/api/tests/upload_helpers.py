"""Helpers for M7b upload tests: a recording scanner, the processing run, and real layout-3 files.

The processing job is run in-process with the same blob store the app wrote to; the scanner is a
fake unless a test talks to the live clamd. Synthetic people and data only.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID

import pypdfium2 as pdfium
from flask.testing import FlaskClient
from PIL import Image, ImageDraw
from sqlalchemy import Engine, text
from werkzeug.test import TestResponse

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.extraction.identifier import PrescriptionIdentifierReader
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.pdf.weasy import WeasyPrintRenderer
from mediease_api.application.uploads.processing import ProcessUpload, SweepUploads
from mediease_api.domain.clinics.clinic import PaperSize
from mediease_api.domain.jobs.job import PROCESS_UPLOAD_KIND, UPLOAD_SWEEP_KIND, ClaimedJob
from mediease_api.domain.prescriptions.document import build_document
from mediease_api.domain.uploads.checks import ScannerUnavailable, ScanResult
from mediease_api.ports.uploads import IdentifierReaderPort, MalwareScannerPort
from tests.conftest import UowFactory
from tests.integration.test_clinic_applications_http import MemoryStore
from tests.integration.test_portal_http import portal_csrf
from tests.portal_helpers import PORTAL
from tests.unit.domain.test_rx_document import patient_of

UPL = f"{PORTAL}/prescription-uploads"
SENTINEL = "EDITED-SENTINEL-TABLET"


@dataclass
class FakeScanner:
    """Clean unless told otherwise; records what it was given."""

    result: ScanResult | Exception = field(default_factory=lambda: ScanResult(clean=True))
    scanned: list[bytes] = field(default_factory=list)

    def scan(self, data: bytes) -> ScanResult:
        self.scanned.append(data)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


UNAVAILABLE = ScannerUnavailable()


def upload(client: FlaskClient, data: bytes, name: str = "prescription.pdf") -> TestResponse:
    return client.post(
        UPL,
        data={"file": (io.BytesIO(data), name)},
        content_type="multipart/form-data",
        headers=portal_csrf(client),
    )


def by_code(client: FlaskClient, code: str) -> TestResponse:
    return client.post(f"{UPL}/by-code", json={"code": code}, headers=portal_csrf(client))


def challenge(client: FlaskClient, upload_id: str, digits: str) -> TestResponse:
    return client.post(
        f"{UPL}/{upload_id}/challenge", json={"phone_last4": digits}, headers=portal_csrf(client)
    )


def select(client: FlaskClient, upload_id: str, choice: str) -> TestResponse:
    return client.post(
        f"{UPL}/{upload_id}/selection", json={"choice": choice}, headers=portal_csrf(client)
    )


def withdraw(client: FlaskClient, upload_id: str) -> TestResponse:
    return client.delete(f"{UPL}/{upload_id}", headers=portal_csrf(client))


def state_of(client: FlaskClient, upload_id: str) -> dict[str, Any]:
    resp = client.get(f"{UPL}/{upload_id}")
    assert resp.status_code == 200, resp.get_json()
    body: dict[str, Any] = resp.get_json()
    return body


def process(
    db: Engine,
    uow_factory: UowFactory,
    store: MemoryStore,
    *,
    scanner: MalwareScannerPort | None = None,
    reader: IdentifierReaderPort | None = None,
    attempts: int = 1,
    max_attempts: int = 4,
    keep: bool = False,
) -> None:
    """Run every queued upload job once, as the upload worker would, then drop the rows."""
    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT id, payload FROM jobs WHERE kind = :k AND state = 'queued'"),
            {"k": PROCESS_UPLOAD_KIND},
        ).all()
    handler = ProcessUpload(
        uow=uow_factory(),
        clock=SystemClock(),
        ids=Uuid7Generator(),
        storage=store,
        scanner=scanner or FakeScanner(),
        reader=reader or PrescriptionIdentifierReader(),
    )
    for row in rows:
        handler(
            ClaimedJob(
                id=row.id,
                kind=PROCESS_UPLOAD_KIND,
                clinic_id=None,
                payload=row.payload,
                attempts=attempts,
                max_attempts=max_attempts,
                request_id=None,
                locked_by="test",
            )
        )
    if not keep:
        with db.begin() as conn:
            conn.execute(text("DELETE FROM jobs WHERE kind = :k"), {"k": PROCESS_UPLOAD_KIND})


def sweep(uow_factory: UowFactory, store: MemoryStore) -> None:
    SweepUploads(uow=uow_factory(), clock=SystemClock(), storage=store)(
        ClaimedJob(
            id=Uuid7Generator().new_id(),
            kind=UPLOAD_SWEEP_KIND,
            clinic_id=None,
            payload={},
            attempts=1,
            max_attempts=1,
            request_id=None,
            locked_by="test",
        )
    )


@dataclass(frozen=True)
class FixedReader:
    """An identifier reader that 'finds' the given IDs (for decisions, not for decoding)."""

    ids: Sequence[UUID]

    def read(self, data: bytes, content_type: str) -> Any:
        from mediease_api.domain.uploads.checks import IdentifierRead, ReadMethod

        return IdentifierRead(ids=frozenset(self.ids), methods=frozenset({ReadMethod.QR}))


def edited_pdf(uow_factory: UowFactory, clinic_id: UUID, rx_id: UUID) -> bytes:
    """The real version's layout-3 PDF, its genuine ID and QR, with the medicine text changed."""
    with uow_factory() as uow:
        rx = uow.tenant(clinic_id).prescriptions.get(rx_id)
        assert rx is not None
    rx.items = tuple(
        replace(item, medicine_name=SENTINEL, dose="900 mg", duration_days=90) for item in rx.items
    )
    doc = build_document(rx, patient_of(rx), paper_size=PaperSize.A5, timezone="Asia/Kolkata")
    return WeasyPrintRenderer().render(doc)


def photo_of(pdf: bytes, *, scribble: str | None = SENTINEL, qr: bool = True) -> bytes:
    """A 'photo' (PNG, no text layer) of the PDF's first page; optionally written over, or with
    the QR covered."""
    document = pdfium.PdfDocument(pdf)
    try:
        image: Image.Image = document[0].render(scale=3).to_pil().convert("RGB")
    finally:
        document.close()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    if scribble is not None:
        draw.rectangle((0, height * 0.2, width, height * 0.6), fill="white")
        draw.text((40, height * 0.3), f"{scribble} 900 mg for 90 days", fill="black")
    if not qr:
        draw.rectangle((0, height * 0.8, width, height), fill="white")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()
