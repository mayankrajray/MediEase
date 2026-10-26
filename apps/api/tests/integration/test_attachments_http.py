"""Reports attached to visits over HTTP (M6d-P6; FR-VIS-04; spec visit-attachments AC1-AC9).

Real PostgreSQL and the local blob store. Completed visits are written through the repositories
(``_past_visit``).
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from tests.conftest import UowFactory, World, make_db_app
from tests.integration.test_appointments_http import _patient
from tests.integration.test_clinic_applications_http import MemoryStore
from tests.integration.test_visits_http import _past_visit, _send
from tests.portal_helpers import link_by_invite, portal_client

PDF = b"%PDF-1.7\n%synthetic report\n" + b"0" * 256
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
NAME = "SENTINEL-hba1c-report.pdf"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _url(visit: UUID | str) -> str:
    return f"/api/v1/visits/{visit}/attachments"


def _upload(
    client: FlaskClient, visit: UUID | str, data: bytes = PDF, name: str = NAME
) -> TestResponse:
    csrf = client.get_cookie("me_csrf", path="/")
    return client.post(
        _url(visit),
        data={"file": (io.BytesIO(data), name)},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf.value} if csrf else {},
    )


def _ok(resp: TestResponse, status: int = 200) -> dict[str, Any]:
    assert resp.status_code == status, resp.get_json()
    body: dict[str, Any] = resp.get_json()
    return body


def _code(resp: TestResponse) -> tuple[int, str]:
    return resp.status_code, str(resp.get_json()["error"]["code"])


def _visit(world: World, uow_factory: UowFactory) -> tuple[UUID, str]:
    patient = _patient(world.client_for(world.a.desk))
    return _past_visit(uow_factory, world, patient, days_ago=0), patient


def _audit(db: Engine) -> list[tuple[str, dict[str, str]]]:
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, metadata FROM audit_events WHERE action LIKE 'visit.attachment%'"
                " ORDER BY occurred_at, id"
            )
        ).all()
    return [(r[0], r[1]) for r in rows]


def test_ac1_ac2_the_desk_attaches_a_report_it_cannot_open_and_the_doctor_opens_it(
    world: World, uow_factory: UowFactory, db: Engine
) -> None:
    desk = world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    owner = world.client_for(world.a.owner)
    visit, _ = _visit(world, uow_factory)

    added = _ok(_upload(desk, visit), 201)
    assert (added["filename"], added["content_type"], added["size_bytes"]) == (
        NAME,
        "application/pdf",
        len(PDF),
    )
    assert added["can_delete"] is True and added["shared_with_patient"] is False
    assert added["uploaded_by_user_id"] == str(world.a.desk.id)

    # D7: the desk adds but never lists or opens (CLINICAL_VIEW).
    file_url = f"{_url(visit)}/{added['id']}/file"
    assert _code(desk.get(_url(visit))) == (403, "PERM_DENIED")
    assert _code(desk.get(file_url)) == (403, "PERM_DENIED")

    listed = _ok(doctor.get(_url(visit)))["items"]
    assert [(i["id"], i["can_delete"]) for i in listed] == [(added["id"], False)]
    assert [i["id"] for i in _ok(owner.get(_url(visit)))["items"]] == [added["id"]]

    opened = doctor.get(file_url)
    assert opened.status_code == 200 and opened.data == PDF
    assert opened.mimetype == "application/pdf"
    assert opened.headers["X-Content-Type-Options"] == "nosniff"
    assert opened.headers["Content-Security-Policy"] == "sandbox; default-src 'none'"
    assert opened.headers["Cache-Control"] == "private, no-store"
    assert opened.headers["Content-Disposition"].startswith(f'inline; filename="{NAME}"')

    # R13: audited on every open; IDs, type and size only, never the name.
    events = _audit(db)
    assert [e[0] for e in events] == ["visit.attachment_added", "visit.attachment_opened"]
    assert events[0][1] == {
        "attachment_id": added["id"],
        "content_type": "application/pdf",
        "size_bytes": str(len(PDF)),
    }
    assert all("SENTINEL" not in str(e[1]) for e in events)
    doctor.get(file_url)
    assert [e[0] for e in _audit(db)].count("visit.attachment_opened") == 2


def test_ac3_r2_only_pdf_jpeg_or_png_up_to_10_mb_by_their_bytes(
    world: World, uow_factory: UowFactory
) -> None:
    doctor = world.client_for(world.a.doctor_user)
    visit, _ = _visit(world, uow_factory)

    disguised = _upload(doctor, visit, b"<html><script>alert(1)</script>", "report.pdf")
    assert _code(disguised) == (422, "VIS_FILE_REJECTED")
    assert disguised.get_json()["error"]["details"] == {"reason": "type"}
    assert _code(_upload(doctor, visit, b"", "empty.pdf"))[1] == "VIS_FILE_REJECTED"
    too_big = _upload(doctor, visit, b"%PDF-" + b"0" * (10 * 1024 * 1024), "big.pdf")
    assert _code(too_big) == (422, "VIS_FILE_REJECTED")
    assert too_big.get_json()["error"]["details"] == {"reason": "size"}
    huge = _upload(doctor, visit, b"%PDF-" + b"0" * (11 * 1024 * 1024), "huge.pdf")
    assert _code(huge) == (413, "REQ_REQUEST_ENTITY_TOO_LARGE")
    as_json = _send(doctor, "POST", _url(visit), {"file": "x"})
    assert _code(as_json) == (415, "REQ_UNSUPPORTED_MEDIA_TYPE")

    image = _ok(_upload(doctor, visit, PNG, "x-ray"), 201)
    assert (image["content_type"], image["filename"]) == ("image/png", "x-ray.png")
    assert [i["id"] for i in _ok(doctor.get(_url(visit)))["items"]] == [image["id"]]


def test_ac4_r8_the_uploader_deletes_within_24_hours_and_then_it_stays(
    world: World, uow_factory: UowFactory, db: Engine
) -> None:
    desk = world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    visit, _ = _visit(world, uow_factory)
    first = _ok(_upload(desk, visit), 201)
    second = _ok(_upload(desk, visit), 201)

    assert _code(_send(doctor, "DELETE", f"{_url(visit)}/{first['id']}")) == (
        403,
        "VIS_ATTACHMENT_NOT_YOURS",
    )
    assert _send(desk, "DELETE", f"{_url(visit)}/{first['id']}").status_code == 204
    assert _code(doctor.get(f"{_url(visit)}/{first['id']}/file")) == (404, "REQ_NOT_FOUND")
    assert _code(_send(desk, "DELETE", f"{_url(visit)}/{first['id']}")) == (404, "REQ_NOT_FOUND")
    assert [i["id"] for i in _ok(doctor.get(_url(visit)))["items"]] == [second["id"]]

    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE visit_attachments SET uploaded_at = uploaded_at - interval '25 hours'"
                " WHERE id = :id"
            ),
            {"id": second["id"]},
        )
    late = _send(desk, "DELETE", f"{_url(visit)}/{second['id']}")
    assert _code(late) == (409, "VIS_ATTACHMENT_LOCKED")
    with db.connect() as conn:
        kept = conn.execute(
            text("SELECT deleted_at IS NOT NULL, deleted_by FROM visit_attachments WHERE id = :id"),
            {"id": first["id"]},
        ).one()
    assert kept == (True, world.a.desk.id)
    assert "visit.attachment_deleted" in [e[0] for e in _audit(db)]


def test_ac5_r3_a_visit_holds_at_most_20_reports(world: World, uow_factory: UowFactory) -> None:
    desk = world.client_for(world.a.desk)
    visit, _ = _visit(world, uow_factory)
    for _ in range(20):
        _ok(_upload(desk, visit, PNG, "scan.png"), 201)
    assert _code(_upload(desk, visit, PNG, "scan.png")) == (409, "VIS_ATTACHMENT_LIMIT")


def test_ac6_ac7_r10_r12_the_visits_doctor_shares_a_report_with_the_portal(
    world: World, uow_factory: UowFactory, db: Engine
) -> None:
    desk = world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    owner = world.client_for(world.a.owner)
    visit, patient = _visit(world, uow_factory)
    report = _ok(_upload(desk, visit), 201)
    kept = _ok(_upload(desk, visit, PNG, "private.png"), 201)
    share = f"{_url(visit)}/{report['id']}/share"

    account = portal_client(world, email="asha.reports@example.test")
    link_by_invite(desk, account, patient)
    assert _ok(account.get("/api/v1/portal/attachments"))["items"] == []

    # Only the visit's doctor shares (the desk and an owner who is not a doctor cannot).
    assert _code(_send(desk, "PUT", share, {"shared": True})) == (403, "PERM_DENIED")
    assert _code(_send(owner, "PUT", share, {"shared": True})) == (403, "PERM_DENIED")
    shared = _ok(_send(doctor, "PUT", share, {"shared": True}))
    assert shared["shared_with_patient"] is True and shared["shared_at"]
    _ok(_send(doctor, "PUT", share, {"shared": True}))  # again: no change, no audit row

    listed = _ok(account.get("/api/v1/portal/attachments"))["items"]
    assert [(i["id"], i["filename"], i["clinic_name"]) for i in listed] == [
        (report["id"], NAME, world.a.clinic.name)
    ]
    got = account.get(f"/api/v1/portal/attachments/{report['id']}/file")
    assert got.status_code == 200 and got.data == PDF
    assert got.headers["X-Content-Type-Options"] == "nosniff"
    assert got.headers["Content-Security-Policy"] == "sandbox; default-src 'none'"
    # A report that was not shared is not found.
    unshared = account.get(f"/api/v1/portal/attachments/{kept['id']}/file")
    assert _code(unshared) == (404, "REQ_NOT_FOUND")

    _ok(_send(doctor, "PUT", share, {"shared": False}))
    assert _ok(account.get("/api/v1/portal/attachments"))["items"] == []
    gone = account.get(f"/api/v1/portal/attachments/{report['id']}/file")
    assert _code(gone) == (404, "REQ_NOT_FOUND")
    actions = [e[0] for e in _audit(db)]
    assert (
        actions.count("visit.attachment_shared"),
        actions.count("visit.attachment_unshared"),
    ) == (
        1,
        1,
    )


def test_ac8_another_clinics_visit_and_report_are_not_found(
    world: World, uow_factory: UowFactory
) -> None:
    desk_a = world.client_for(world.a.desk)
    visit, _ = _visit(world, uow_factory)
    report = _ok(_upload(desk_a, visit), 201)

    doctor_b = world.client_for(world.b.doctor_user)
    desk_b = world.client_for(world.b.desk)
    assert _code(_upload(desk_b, visit)) == (404, "REQ_NOT_FOUND")
    assert _code(doctor_b.get(_url(visit))) == (404, "REQ_NOT_FOUND")
    assert _code(doctor_b.get(f"{_url(visit)}/{report['id']}/file")) == (404, "REQ_NOT_FOUND")


class _BrokenStore(MemoryStore):
    """A blob store that refuses writes, or deletes (R4: nothing is kept half-done)."""

    def __init__(self, *, put_fails: bool = True) -> None:
        super().__init__()
        self._put_fails = put_fails

    def put(self, key: str, data: bytes, *, content_type: str) -> bool:
        if self._put_fails:
            raise OSError("disk full")
        return super().put(key, data, content_type=content_type)

    def delete(self, key: str) -> None:
        raise OSError("bucket unreachable")


def test_r4_a_file_that_cannot_be_stored_leaves_nothing_behind(
    world: World, uow_factory: UowFactory, migrated_database_url: str
) -> None:
    visit, _ = _visit(world, uow_factory)
    broken = replace(world, app=make_db_app(migrated_database_url, blob_storage=_BrokenStore()))
    desk = broken.client_for(world.a.desk)
    assert _code(_upload(desk, visit)) == (503, "VIS_UPLOAD_FAILED")
    doctor = world.client_for(world.a.doctor_user)
    assert _ok(doctor.get(_url(visit)))["items"] == []

    # A delete whose file cannot be removed still hides the report (the row says deleted).
    keeps = replace(
        world, app=make_db_app(migrated_database_url, blob_storage=_BrokenStore(put_fails=False))
    )
    desk = keeps.client_for(world.a.desk)
    added = _ok(_upload(desk, visit), 201)
    assert _send(desk, "DELETE", f"{_url(visit)}/{added['id']}").status_code == 204
    assert _ok(keeps.client_for(world.a.doctor_user).get(_url(visit)))["items"] == []
