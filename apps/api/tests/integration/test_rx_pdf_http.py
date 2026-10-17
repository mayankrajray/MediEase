"""Printing prescriptions over HTTP (M4-P4; FR-RX-04, 06; spec R8, R16, R18, D6, AC8, AC10).

Real WeasyPrint against the real database; a counting renderer where the number of renders is
the point (AC8) and a failing one for RX_PDF_FAILED.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pypdfium2 as pdfium
import pytest
from sqlalchemy import Engine, create_engine, text

from mediease_api.adapters.pdf.weasy import WeasyPrintRenderer
from mediease_api.application.prescriptions.pdf import DownloadPrescriptionPdf
from mediease_api.domain.prescriptions.document import RxDocument
from mediease_api.domain.prescriptions.errors import PdfBusy
from tests.conftest import World, make_db_app
from tests.integration.test_appointments_http import _in_parallel
from tests.integration.test_prescriptions_http import (
    SENTINEL,
    _audit,
    _code,
    _draft,
    _fill,
    _issued,
)
from tests.integration.test_visits_http import _send


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


class CountingRenderer:
    """The real renderer, counted and slowed so concurrent first downloads overlap."""

    def __init__(self, delay: float = 0.3, *, fail: bool = False) -> None:
        self._real = WeasyPrintRenderer()
        self._delay = delay
        self._fail = fail
        self._lock = threading.Lock()
        self.calls = 0

    def render(self, document: RxDocument) -> bytes:
        with self._lock:
            self.calls += 1
        time.sleep(self._delay)
        if self._fail:
            raise RuntimeError("renderer down")
        return self._real.render(document)


def _with(world: World, migrated_database_url: str, **adapters: Any) -> World:
    return replace(world, app=make_db_app(migrated_database_url, **adapters))


def _pdf_text(data: bytes) -> str:
    document = pdfium.PdfDocument(data)
    try:
        return "\n".join(p.get_textpage().get_text_range() for p in document)
    finally:
        document.close()


def _key(db: Engine, rx_id: str) -> str | None:
    with db.connect() as conn:
        value = conn.execute(
            text("SELECT pdf_object_key FROM prescriptions WHERE id = :id"), {"id": rx_id}
        ).scalar()
    return None if value is None else str(value)


# --- R8, R18: the PDF ----------------------------------------------------------------------------


def test_r8_r18_the_doctor_downloads_the_pdf_rendered_once_and_stored(
    world: World, db: Engine
) -> None:
    doctor, _, rx = _issued(world)
    url = f"/api/v1/prescriptions/{rx['id']}/pdf"
    first = doctor.get(url)
    assert first.status_code == 200
    assert first.mimetype == "application/pdf"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert first.headers["Content-Disposition"] == (
        f'inline; filename="prescription-{rx["id"]}-v1.pdf"'
    )
    content = _pdf_text(first.data)
    assert "Syrup X" in content and "How to give" in content
    assert "10 ml boiled cooled water" in content  # the doctor's amount, as typed
    assert rx["doctor_snapshot"]["registration_number"] in content
    assert "Digitally generated via MediEase" in content
    assert _key(db, rx["id"]) == f"rx/{world.a.clinic.id}/{rx['id']}/v1.pdf"

    again = doctor.get(url)
    assert again.data == first.data
    rows = _audit(db, "prescription.pdf_downloaded")
    assert [m["rendered"] for _, m in rows] == ["true", "false"]
    assert {m["role"] for _, m in rows} == {"DOCTOR"}
    assert all(set(m) == {"visit_id", "version", "role", "rendered"} for _, m in rows)


def test_ac8_two_concurrent_first_downloads_render_once_with_identical_bytes(
    world: World, db: Engine, migrated_database_url: str
) -> None:
    renderer = CountingRenderer()
    counted = _with(world, migrated_database_url, pdf_renderer=renderer)
    doctor, _, rx = _issued(counted)
    desk = counted.client_for(counted.a.desk)
    url = f"/api/v1/prescriptions/{rx['id']}/pdf"
    results = _in_parallel([lambda: doctor.get(url), lambda: desk.get(url)])
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].data == results[1].data
    assert renderer.calls == 1
    assert desk.get(url).data == results[0].data and renderer.calls == 1


# --- D6, decisions 1A and 2A: front desk prints --------------------------------------------------


def test_d6_front_desk_prints_an_issued_prescription_without_reading_it(
    world: World, db: Engine
) -> None:
    _, visit, rx = _issued(world)
    desk = world.client_for(world.a.desk)
    assert desk.get(f"/api/v1/prescriptions/{rx['id']}").status_code == 403
    listed = desk.get(f"/api/v1/patients/{visit['patient_id']}/prescriptions")
    assert listed.status_code == 200 and listed.headers["Cache-Control"] == "no-store"
    [row] = listed.get_json()["items"]
    assert set(row) == {"id", "visit_id", "version", "issued_at", "doctor_display_name"}
    assert (row["id"], row["version"]) == (rx["id"], 1)

    printed = desk.get(f"/api/v1/prescriptions/{rx['id']}/pdf")
    assert printed.status_code == 200
    [(_, meta)] = _audit(db, "prescription.pdf_downloaded")
    assert meta["role"] == "FRONT_DESK"


def test_d6_a_draft_is_never_printed(world: World) -> None:
    doctor, visit, rx = _draft(world)
    _fill(doctor, rx)
    for client in (doctor, world.client_for(world.a.desk)):
        resp = client.get(f"/api/v1/prescriptions/{rx['id']}/pdf")
        assert (resp.status_code, _code(resp)) == (409, "RX_NOT_ISSUED")
    desk = world.client_for(world.a.desk)
    listed = desk.get(f"/api/v1/patients/{visit['patient_id']}/prescriptions")
    assert listed.get_json()["items"] == []


def test_decision_1a_front_desk_prints_only_the_latest_version(world: World) -> None:
    doctor, visit, rx = _issued(world)
    revised = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise").get_json()
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{revised['id']}/issue", {"revision": 1})
    assert issued.status_code == 200, issued.get_json()

    desk = world.client_for(world.a.desk)
    old = desk.get(f"/api/v1/prescriptions/{rx['id']}/pdf")
    assert (old.status_code, _code(old)) == (409, "RX_NOT_LATEST")
    assert old.get_json()["error"]["details"] == {"latest_id": revised["id"]}
    current = desk.get(f"/api/v1/prescriptions/{revised['id']}/pdf")
    assert current.status_code == 200
    assert "Revised prescription (version 2)" in _pdf_text(current.data)
    listed = desk.get(f"/api/v1/patients/{visit['patient_id']}/prescriptions").get_json()
    assert [r["id"] for r in listed["items"]] == [revised["id"]]

    # Clinicians may still print the superseded version (it is a record).
    owner = world.client_for(world.a.owner)
    assert owner.get(f"/api/v1/prescriptions/{rx['id']}/pdf").status_code == 200


# --- Decision 3A: paper size ---------------------------------------------------------------------


def test_decision_3a_paper_size_applies_at_first_render_and_then_stays(world: World) -> None:
    doctor, _, rx = _issued(world)
    owner = world.client_for(world.a.owner)
    a5 = doctor.get(f"/api/v1/prescriptions/{rx['id']}/pdf").data

    changed = _send(owner, "PATCH", "/api/v1/clinic", {"rx_paper_size": "A4"})
    assert changed.status_code == 200 and changed.get_json()["rx_paper_size"] == "A4"
    assert doctor.get(f"/api/v1/prescriptions/{rx['id']}/pdf").data == a5  # already printed

    def width(data: bytes) -> int:
        document = pdfium.PdfDocument(data)
        try:
            return round(document[0].get_size()[0])
        finally:
            document.close()

    assert width(a5) == 420  # A5 portrait, in points
    revised = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise").get_json()
    _send(doctor, "POST", f"/api/v1/prescriptions/{revised['id']}/issue", {"revision": 1})
    assert width(doctor.get(f"/api/v1/prescriptions/{revised['id']}/pdf").data) == 595  # A4


def test_paper_size_is_validated_and_owner_only(world: World) -> None:
    owner, desk = world.client_for(world.a.owner), world.client_for(world.a.desk)
    bad = _send(owner, "PATCH", "/api/v1/clinic", {"rx_paper_size": "Letter"})
    assert (bad.status_code, _code(bad)) == (422, "REQ_VALIDATION_FAILED")
    assert _send(desk, "PATCH", "/api/v1/clinic", {"rx_paper_size": "A4"}).status_code == 403


# --- R18 failures --------------------------------------------------------------------------------


def test_r18_a_failed_render_stores_nothing_and_the_next_download_tries_again(
    world: World, db: Engine, migrated_database_url: str
) -> None:
    broken = _with(world, migrated_database_url, pdf_renderer=CountingRenderer(0, fail=True))
    doctor, _, rx = _issued(broken)
    resp = doctor.get(f"/api/v1/prescriptions/{rx['id']}/pdf")
    assert (resp.status_code, _code(resp)) == (500, "RX_PDF_FAILED")
    assert resp.get_json()["error"]["details"] == {"stage": "render"}
    assert _key(db, rx["id"]) is None
    assert _audit(db, "prescription.pdf_downloaded") == []

    healthy = world.client_for(world.a.doctor_user)
    assert healthy.get(f"/api/v1/prescriptions/{rx['id']}/pdf").status_code == 200
    assert _key(db, rx["id"]) is not None


def test_r18_a_long_wait_for_the_render_lock_is_busy_with_retry_after(
    world: World, db: Engine
) -> None:
    doctor, _, rx = _issued(world)
    started, release = threading.Event(), threading.Event()

    def hold_lock() -> None:
        with db.connect() as conn, conn.begin():
            conn.execute(
                text("SELECT 1 FROM prescriptions WHERE id = :id FOR UPDATE"), {"id": rx["id"]}
            )
            started.set()
            release.wait(10)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    try:
        assert started.wait(5)
        original = DownloadPrescriptionPdf.__init__

        def short_wait(self: DownloadPrescriptionPdf, **kwargs: Any) -> None:
            original(self, **{**kwargs, "wait_seconds": 1})

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(DownloadPrescriptionPdf, "__init__", short_wait)
            resp = doctor.get(f"/api/v1/prescriptions/{rx['id']}/pdf")
        assert (resp.status_code, _code(resp)) == (503, "RX_PDF_BUSY")
        assert resp.headers["Retry-After"] == str(PdfBusy.retry_after_seconds)
    finally:
        release.set()
        holder.join()
    assert doctor.get(f"/api/v1/prescriptions/{rx['id']}/pdf").status_code == 200


# --- R17: nothing clinical leaks -----------------------------------------------------------------


def test_r17_downloading_logs_and_audits_no_prescription_text(
    world: World, db: Engine, json_logs: Any
) -> None:
    doctor, _, rx = _draft(world)
    _fill(doctor, rx, items=[{"medicine_name": SENTINEL, "notes": SENTINEL}])
    _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    resp = doctor.get(f"/api/v1/prescriptions/{rx['id']}/pdf")
    assert resp.status_code == 200 and SENTINEL in _pdf_text(resp.data)
    assert SENTINEL not in "".join(str(e) for e in json_logs())
    with db.connect() as conn:
        dumped = conn.execute(text("SELECT metadata::text FROM audit_events")).scalars().all()
    assert all(SENTINEL not in m for m in dumped)


def test_another_clinics_patient_list_is_404(world: World) -> None:
    _, visit, _ = _issued(world)
    owner_of_b = world.client_for(world.b.owner)
    resp = owner_of_b.get(f"/api/v1/patients/{visit['patient_id']}/prescriptions")
    assert resp.status_code == 404
