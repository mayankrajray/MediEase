"""The ops patient import over HTTP on PostgreSQL (M2-P4; FR-PAT-08, FR-OPS-02, spec R8, §2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from werkzeug.test import TestResponse

from mediease_api.delivery.http.ops import MAX_IMPORT_BYTES
from mediease_api.domain.identity.membership import Role
from tests.conftest import World

SessionFactory = sessionmaker[Session]
HEADER = "name,phone,sex,dob_or_age,guardian_name,language\n"
FILE = (
    HEADER
    + "Zubin Quillfeather,9123456780,M,1984-02-29,,en\n"
    + "Tara Quillfeather,9123456780,F,7,Zubin Quillfeather,hi\n"
    + "Nobody,not-a-phone,F,30,,\n"
)


def _imports(clinic_id: object) -> str:
    return f"/api/v1/ops/clinics/{clinic_id}/patient-imports"


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def _post(
    client: FlaskClient,
    clinic_id: object,
    body: str | bytes = FILE,
    *,
    query: str = "",
    content_type: str = "text/csv; charset=utf-8",
) -> TestResponse:
    data = body.encode() if isinstance(body, str) else body
    return client.post(
        _imports(clinic_id) + query, data=data, content_type=content_type, headers=_csrf(client)
    )


def _error(resp: TestResponse) -> dict[str, Any]:
    return dict(resp.get_json()["error"])


def test_fr_pat_08_without_the_flag_it_is_a_dry_run(world: World) -> None:
    ops = world.client_for(world.ops)

    resp = _post(ops, world.a.clinic.id)

    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.get_json() == {
        "dry_run": True,
        "rows": 3,
        "valid": 2,
        "invalid": 1,
        "possible_duplicates": 1,
        "already_registered": 0,
        "imported": 0,
        "codes": [],
        "errors": [{"row": 4, "field": "phone", "reason": "is not a valid phone number"}],
        "duplicates": [{"row": 3, "kind": "earlier_row", "same_as_row": 2}],
        "errors_truncated": False,
        "duplicates_truncated": False,
    }
    desk = world.client_for(world.a.desk)
    assert desk.get("/api/v1/patients?q=9123456780").get_json()["items"] == []


def test_fr_pat_08_a_commit_imports_and_the_clinic_finds_them(
    world: World, session_factory: SessionFactory
) -> None:
    ops = world.client_for(world.ops)

    resp = _post(ops, world.a.clinic.id, query="?dry_run=false")

    assert resp.status_code == 200
    body = resp.get_json()
    assert (body["dry_run"], body["imported"], len(body["codes"])) == (False, 2, 2)
    found = world.client_for(world.a.desk).get("/api/v1/patients?q=9123456780").get_json()
    assert sorted(p["code"] for p in found["items"]) == sorted(body["codes"])
    tara = next(p for p in found["items"] if p["full_name"] == "Tara Quillfeather")
    assert (tara["guardian_name"], tara["language"], tara["whatsapp_allowed"]) == (
        "Zubin Quillfeather",
        "hi",
        False,
    )
    # Clinic B is untouched (NFR-08).
    assert world.client_for(world.b.owner).get("/api/v1/patients?q=9123456780").get_json() == {
        "items": []
    }
    with session_factory() as session:
        rows = session.execute(
            text(
                "SELECT clinic_id, actor_type, metadata FROM audit_events "
                "WHERE action = 'patient.imported'"
            )
        ).all()
    assert len(rows) == 2
    assert {(r.clinic_id, r.actor_type) for r in rows} == {(world.a.clinic.id, "OPS")}
    assert "Quillfeather" not in str([r.metadata for r in rows])


@pytest.mark.parametrize("query", ["?dry_run=true", "?dry_run=TRUE", ""])
def test_r8_a_dry_run_writes_nothing_however_it_is_asked_for(world: World, query: str) -> None:
    ops = world.client_for(world.ops)

    assert _post(ops, world.a.clinic.id, query=query).get_json()["dry_run"] is True
    assert _post(ops, world.a.clinic.id, query="?dry_run=false").get_json()["imported"] == 2


def test_the_dry_run_flag_must_be_true_or_false(world: World) -> None:
    resp = _post(world.client_for(world.ops), world.a.clinic.id, query="?dry_run=yes")

    assert resp.status_code == 422
    assert _error(resp)["details"] == {
        "fields": [{"field": "dry_run", "reason": "must be true or false"}]
    }


def test_r8_a_bad_header_is_422_with_the_problems_and_imports_nothing(world: World) -> None:
    ops = world.client_for(world.ops)

    resp = _post(
        ops, world.a.clinic.id, "name,phone,diagnosis\nZubin,9123456780,x\n", query="?dry_run=false"
    )

    assert resp.status_code == 422
    error = _error(resp)
    assert error["code"] == "PAT_IMPORT_INVALID"
    assert "column 3 is not one of" in error["details"]["problems"][0]
    assert "diagnosis" not in str(error) and "Zubin" not in str(error)


def test_only_text_csv_is_accepted(world: World) -> None:
    ops = world.client_for(world.ops)

    for content_type in ("application/json", "multipart/form-data", "text/plain"):
        resp = _post(ops, world.a.clinic.id, content_type=content_type)
        assert resp.status_code == 415, content_type
        assert _error(resp)["code"] == "REQ_UNSUPPORTED_MEDIA_TYPE"


def test_a_file_over_two_megabytes_is_413(world: World) -> None:
    ops = world.client_for(world.ops)
    too_big = HEADER + "x" * MAX_IMPORT_BYTES

    resp = _post(ops, world.a.clinic.id, too_big)

    assert resp.status_code == 413
    assert _error(resp)["code"] == "REQ_REQUEST_ENTITY_TOO_LARGE"


def test_the_body_limit_is_this_routes_only(world: World) -> None:
    # Two megabytes of JSON elsewhere is not refused for size (it fails validation instead).
    owner = world.client_for(world.a.owner)
    resp = owner.patch(
        "/api/v1/clinic", json={"city": "x" * (MAX_IMPORT_BYTES + 10)}, headers=_csrf(owner)
    )
    assert resp.status_code == 422


def test_an_unknown_clinic_is_404(world: World) -> None:
    resp = _post(world.client_for(world.ops), "00000000-0000-0000-0000-000000000001")

    assert resp.status_code == 404
    assert _error(resp)["code"] == "REQ_NOT_FOUND"


@pytest.mark.parametrize("role", list(Role))
def test_r10_spec_2_clinic_staff_cannot_import_even_into_their_own_clinic(
    world: World, role: Role
) -> None:
    resp = _post(
        world.client_for(world.a.user_for(role)), world.a.clinic.id, query="?dry_run=false"
    )

    assert resp.status_code == 403
    assert world.client_for(world.a.desk).get("/api/v1/patients?q=9123456780").get_json() == {
        "items": []
    }


def test_anonymous_and_csrf_less_imports_are_refused(world: World) -> None:
    assert (
        world.anonymous()
        .post(_imports(world.a.clinic.id), data=FILE, content_type="text/csv")
        .status_code
        == 401
    )
    ops = world.client_for(world.ops)
    no_csrf = ops.post(_imports(world.a.clinic.id), data=FILE, content_type="text/csv")
    assert no_csrf.status_code == 403
    assert _error(no_csrf)["code"] == "AUTH_CSRF_INVALID"


def test_d5_an_import_puts_no_names_or_phones_in_the_logs(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    ops = world.client_for(world.ops)
    capsys.readouterr()

    _post(ops, world.a.clinic.id)
    _post(ops, world.a.clinic.id, query="?dry_run=false")

    logged = capsys.readouterr().out
    assert "Quillfeather" not in logged and "9123456780" not in logged
    assert "patient.import_dry_run" in logged and "patient.import_committed" in logged


SAMPLE = Path(__file__).resolve().parents[4] / "scripts" / "fixtures" / "patients-import-sample.csv"


def test_runbook_10_the_sample_file_shows_every_kind_of_report_entry(world: World) -> None:
    report = _post(world.client_for(world.ops), world.a.clinic.id, SAMPLE.read_bytes()).get_json()

    assert (report["rows"], report["valid"], report["invalid"]) == (10, 8, 2)
    assert {(e["row"], e["field"]) for e in report["errors"]} == {
        (8, "guardian_name"),
        (9, "phone"),
    }
    kinds = {d["kind"] for d in report["duplicates"]}
    assert {"earlier_row", "already_registered"} <= kinds
