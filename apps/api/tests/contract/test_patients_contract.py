"""Patients: real responses validated against contracts/openapi.yaml (ADR-0008; M2-P2)."""

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

from tests.conftest import World

_SPEC_PATH = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
_BASE_URL = "http://localhost:8000"
PATIENTS = "/api/v1/patients"
NEW_PATIENT = {
    "full_name": "Asha Rao",
    "phone": "9000000001",
    "sex": "FEMALE",
    "date_of_birth": "1990-05-17",
}


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
                query_string=sent.query_string.decode(),
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
    client: FlaskClient,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
) -> TestResponse:
    headers = {}
    csrf = client.get_cookie("me_csrf", domain="localhost", path="/")
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf.value
    resp = client.open(
        path, method=method, base_url=_BASE_URL, json=body, headers=headers, query_string=query
    )
    resp.sent_body = b"" if body is None else dumps(body).encode()  # type: ignore[attr-defined]
    return resp


def test_adr_0008_the_patient_endpoints_match_the_contract(openapi: OpenAPI, world: World) -> None:
    desk = world.client_for(world.a.desk)

    created = _send(desk, "POST", PATIENTS, NEW_PATIENT)
    assert created.status_code == 201
    _check(openapi, created)
    patient_id = created.get_json()["id"]

    found = _send(desk, "GET", PATIENTS, query={"q": "asha"})
    assert found.status_code == 200
    _check(openapi, found)

    one = _send(desk, "GET", f"{PATIENTS}/{patient_id}")
    assert one.status_code == 200
    _check(openapi, one)

    edited = _send(desk, "PATCH", f"{PATIENTS}/{patient_id}", {"full_name": "Asha R. Rao"})
    assert edited.status_code == 200
    _check(openapi, edited)

    by_age = _send(
        desk,
        "POST",
        PATIENTS,
        {
            **NEW_PATIENT,
            "phone": "9000000002",
            "date_of_birth": None,
            "age_years": 7,
            "guardian_name": "Meera Rao",
        },
    )
    assert by_age.status_code == 201
    _check(openapi, by_age)


def test_adr_0008_the_duplicate_phone_409_carries_candidates_in_the_documented_shape(
    openapi: OpenAPI, world: World
) -> None:
    desk = world.client_for(world.a.desk)
    assert _send(desk, "POST", PATIENTS, NEW_PATIENT).status_code == 201

    duplicate = _send(desk, "POST", PATIENTS, {**NEW_PATIENT, "full_name": "Arun Rao"})

    assert duplicate.status_code == 409
    _check(openapi, duplicate)
    assert len(duplicate.get_json()["error"]["details"]["candidates"]) == 1


def test_adr_0008_the_error_responses_match_the_contract(openapi: OpenAPI, world: World) -> None:
    desk = world.client_for(world.a.desk)
    missing = "00000000-0000-0000-0000-000000000001"

    for resp in (
        _send(desk, "GET", f"{PATIENTS}/{missing}"),  # 404
        _send(desk, "PATCH", f"{PATIENTS}/{missing}", {"full_name": "X"}),  # 404
        _send(desk, "POST", PATIENTS, {**NEW_PATIENT, "phone": "12345"}),  # 422 PAT_PHONE_INVALID
        _send(desk, "POST", PATIENTS, {**NEW_PATIENT, "date_of_birth": "2024-01-01"}),  # guardian
    ):
        assert resp.status_code in (404, 422)
        _check(openapi, resp)

    no_query = _send(desk, "GET", PATIENTS)  # 422: q is required, so the request is invalid too
    assert no_query.status_code == 422
    _check(openapi, no_query, validate_request=False)


def test_adr_0008_an_ops_user_gets_the_documented_403(openapi: OpenAPI, world: World) -> None:
    ops_client = world.client_for(world.ops)

    resp = _send(ops_client, "GET", PATIENTS, query={"q": "a"})

    assert resp.status_code == 403
    _check(openapi, resp)


def test_adr_0008_consent_opt_out_and_opt_in_match_the_contract(
    openapi: OpenAPI, world: World
) -> None:
    desk = world.client_for(world.a.desk)
    patient_id = _send(desk, "POST", PATIENTS, NEW_PATIENT).get_json()["id"]
    consent = {"whatsapp": True, "sms": False}

    for resp, status in (
        (_send(desk, "PUT", f"{PATIENTS}/{patient_id}/consent", consent), 200),
        (_send(desk, "POST", f"{PATIENTS}/{patient_id}/opt-in", consent), 409),  # not opted out
        (_send(desk, "POST", f"{PATIENTS}/{patient_id}/opt-out"), 200),
        (_send(desk, "POST", f"{PATIENTS}/{patient_id}/opt-out"), 200),  # idempotent
        (_send(desk, "PUT", f"{PATIENTS}/{patient_id}/consent", consent), 409),  # opted out
        (_send(desk, "POST", f"{PATIENTS}/{patient_id}/opt-in", consent), 200),
    ):
        assert resp.status_code == status, resp.get_json()
        _check(openapi, resp)
