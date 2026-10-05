"""Contract tests for the ops and invitation endpoints (ADR-0008, M1-P5).

Real responses from the app wired to PostgreSQL are validated against
contracts/openapi.yaml, including the acceptance flow a browser follows with
no session at all.
"""

from __future__ import annotations

from json import dumps
from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient
from openapi_core import OpenAPI
from openapi_core.contrib.werkzeug import WerkzeugOpenAPIRequest, WerkzeugOpenAPIResponse
from werkzeug.test import EnvironBuilder, TestResponse
from werkzeug.wrappers import Request

from tests.conftest import DEMO_PASSWORD, World

_SPEC_PATH = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
_BASE_URL = "http://localhost:8000"
OPS_CLINICS = "/api/v1/ops/clinics"
PASSWORD = "a-new-staff-password"  # gitleaks:allow (synthetic test value)


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    return OpenAPI.from_file_path(str(_SPEC_PATH))


def _check(openapi: OpenAPI, resp: TestResponse, *, validate_request: bool = True) -> None:
    sent = resp.request
    request = WerkzeugOpenAPIRequest(
        Request(
            EnvironBuilder(
                base_url=_BASE_URL,
                path=sent.path,
                method=sent.method,
                headers=dict(sent.headers),
                data=getattr(resp, "sent_body", b""),
            ).get_environ()
        )
    )
    if validate_request:
        openapi.validate_request(request)
    openapi.validate_response(request, WerkzeugOpenAPIResponse(resp))


def _send(
    client: FlaskClient, method: str, path: str, body: dict[str, Any] | None = None
) -> TestResponse:
    headers = {}
    csrf = client.get_cookie("me_csrf", domain="localhost", path="/")
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf.value
    resp = client.open(path, method=method, base_url=_BASE_URL, json=body, headers=headers)
    resp.sent_body = b"" if body is None else dumps(body).encode()  # type: ignore[attr-defined]
    return resp


def _clinic(ops: FlaskClient, slug: str) -> dict[str, Any]:
    resp = _send(ops, "POST", OPS_CLINICS, {"name": "Contract Clinic", "slug": slug})
    assert resp.status_code == 201
    return dict(resp.get_json())


def test_adr_0008_the_ops_onboarding_flow_matches_contract(openapi: OpenAPI, world: World) -> None:
    ops = world.client_for(world.ops)

    created = _send(ops, "POST", OPS_CLINICS, {"name": "Contract Clinic", "slug": "contract-one"})
    assert created.status_code == 201
    _check(openapi, created)

    listed = _send(ops, "GET", OPS_CLINICS)
    assert listed.status_code == 200
    _check(openapi, listed)

    clinic_id = created.get_json()["id"]
    detail = _send(ops, "GET", f"{OPS_CLINICS}/{clinic_id}")
    assert detail.status_code == 200
    _check(openapi, detail)

    doctor = _send(
        ops,
        "POST",
        f"{OPS_CLINICS}/{clinic_id}/doctors",
        {
            "display_name": "Dr. Contract",
            "qualification": "MBBS",
            "registration_number": "CON-1",
            "registration_council": "Sample State Medical Council",
        },
    )
    assert doctor.status_code == 201
    _check(openapi, doctor)

    invited = _send(
        ops,
        "POST",
        f"{OPS_CLINICS}/{clinic_id}/staff-invites",
        {"full_name": "Contract Owner", "role": "OWNER", "email": "contract@example.test"},
    )
    assert invited.status_code == 201
    _check(openapi, invited)

    # The invitee has no session: describe, then accept.
    token = invited.get_json()["accept_url"].rsplit("/", 1)[1]
    invitee = world.anonymous()
    described = _send(invitee, "GET", f"/api/v1/auth/invites/{token}")
    assert described.status_code == 200
    _check(openapi, described)

    accepted = _send(
        invitee, "POST", f"/api/v1/auth/invites/{token}/accept", {"password": PASSWORD}
    )
    assert accepted.status_code == 200
    _check(openapi, accepted)


def test_adr_0008_an_unknown_invitation_matches_contract(openapi: OpenAPI, world: World) -> None:
    resp = _send(world.anonymous(), "GET", "/api/v1/auth/invites/not-a-real-token")
    assert resp.status_code == 404
    _check(openapi, resp)


def test_adr_0008_a_duplicate_slug_matches_contract(openapi: OpenAPI, world: World) -> None:
    ops = world.client_for(world.ops)
    _clinic(ops, "contract-two")
    resp = _send(ops, "POST", OPS_CLINICS, {"name": "Contract Clinic", "slug": "contract-two"})
    assert resp.status_code == 409
    _check(openapi, resp)


def test_adr_0008_clinic_staff_on_the_ops_api_matches_contract(
    openapi: OpenAPI, world: World
) -> None:
    resp = _send(world.client_for(world.a.owner), "GET", OPS_CLINICS)
    assert resp.status_code == 403
    _check(openapi, resp)


def test_adr_0008_the_owner_management_endpoints_match_contract(
    openapi: OpenAPI, world: World
) -> None:
    owner = world.client_for(world.a.owner)

    edited = _send(owner, "PATCH", "/api/v1/clinic", {"city": "Contract City"})
    assert edited.status_code == 200
    _check(openapi, edited)

    doctor = _send(
        owner,
        "POST",
        "/api/v1/clinic/doctors",
        {
            "display_name": "Dr. Owner Added",
            "qualification": "MBBS",
            "registration_number": "OWN-1",
            "registration_council": "Sample State Medical Council",
        },
    )
    assert doctor.status_code == 201
    _check(openapi, doctor)

    updated = _send(
        owner, "PATCH", f"/api/v1/clinic/doctors/{doctor.get_json()['id']}", {"is_active": False}
    )
    assert updated.status_code == 200
    _check(openapi, updated)

    invited = _send(
        owner,
        "POST",
        "/api/v1/clinic/staff",
        {"full_name": "Contract Desk", "role": "FRONT_DESK", "phone": "9000099911"},
    )
    assert invited.status_code == 201
    _check(openapi, invited)

    deactivated = _send(
        owner,
        "PATCH",
        f"/api/v1/clinic/staff/{invited.get_json()['membership_id']}",
        {"status": "DEACTIVATED"},
    )
    assert deactivated.status_code == 200
    _check(openapi, deactivated)


def test_adr_0008_accepting_for_an_existing_account_matches_contract(
    openapi: OpenAPI, world: World
) -> None:
    """R13: the 401 for a wrong current password and the 423 lock are documented shapes."""
    ops = world.client_for(world.ops)
    clinic_id = _clinic(ops, "contract-existing")["id"]
    assert world.a.doctor_user.email is not None
    invited = _send(
        ops,
        "POST",
        f"{OPS_CLINICS}/{clinic_id}/staff-invites",
        {
            "full_name": "Dr. Existing",
            "role": "DOCTOR",
            "email": world.a.doctor_user.email.value,
        },
    )
    assert invited.status_code == 201
    accept = f"/api/v1/auth/invites/{invited.get_json()['accept_url'].rsplit('/', 1)[1]}/accept"
    stranger = world.anonymous()

    for _ in range(4):
        _send(stranger, "POST", accept, {"password": "wrong-guess-password"})
    wrong = _send(stranger, "POST", accept, {"password": "wrong-guess-password"})
    assert wrong.status_code == 401
    _check(openapi, wrong)

    locked = _send(stranger, "POST", accept, {"password": DEMO_PASSWORD})
    assert locked.status_code == 423
    _check(openapi, locked)


# --- Patient import (M2-P4) -------------------------------------------------------------------

IMPORT_FILE = (
    b"name,phone,sex,dob_or_age,guardian_name,language\n"
    b"Contract Person,9000077001,F,30,,en\n"
    b"Contract Child,9000077001,M,5,Contract Person,hi\n"
    b"Bad Row,12,F,30,,\n"
)


def _send_csv(
    client: FlaskClient,
    path: str,
    data: bytes,
    *,
    content_type: str = "text/csv",
) -> TestResponse:
    csrf = client.get_cookie("me_csrf", domain="localhost", path="/")
    assert csrf is not None
    resp = client.post(
        path,
        base_url=_BASE_URL,
        data=data,
        content_type=content_type,
        headers={"X-CSRF-Token": csrf.value},
    )
    resp.sent_body = data  # type: ignore[attr-defined]
    return resp


def test_adr_0008_the_patient_import_matches_contract(openapi: OpenAPI, world: World) -> None:
    ops = world.client_for(world.ops)
    path = f"{OPS_CLINICS}/{world.a.clinic.id}/patient-imports"

    dry = _send_csv(ops, path, IMPORT_FILE)
    assert dry.status_code == 200
    _check(openapi, dry)

    committed = _send_csv(ops, f"{path}?dry_run=false", IMPORT_FILE)
    assert committed.status_code == 200 and committed.get_json()["imported"] == 2
    _check(openapi, committed)

    again = _send_csv(ops, f"{path}?dry_run=false", IMPORT_FILE)
    assert again.get_json()["already_registered"] == 2
    _check(openapi, again)


@pytest.mark.parametrize(
    ("data", "content_type", "status"),
    [
        (b"name,phone\nA,9000077002\n", "text/csv", 422),
        (b"x" * (2 * 1024 * 1024 + 1), "text/csv", 413),
        (b"{}", "application/json", 415),
    ],
)
def test_adr_0008_patient_import_errors_match_contract(
    openapi: OpenAPI, world: World, data: bytes, content_type: str, status: int
) -> None:
    ops = world.client_for(world.ops)
    path = f"{OPS_CLINICS}/{world.a.clinic.id}/patient-imports"

    resp = _send_csv(ops, path, data, content_type=content_type)

    assert resp.status_code == status
    # The 415 and 413 requests are outside the documented request body on purpose.
    _check(openapi, resp, validate_request=status == 422)
