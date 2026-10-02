"""Contract tests for /me and the clinic endpoints (ADR-0008, M1-P3).

Real responses from the app wired to PostgreSQL are validated against
contracts/openapi.yaml — the source of truth for the web client's generated
types — for every success and error shape the endpoints can return.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from flask.testing import FlaskClient
from openapi_core import OpenAPI
from openapi_core.contrib.werkzeug import WerkzeugOpenAPIRequest, WerkzeugOpenAPIResponse
from werkzeug.test import TestResponse

from tests.conftest import World

_SPEC_PATH = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
_BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    return OpenAPI.from_file_path(str(_SPEC_PATH))


def _check(openapi: OpenAPI, resp: TestResponse, *, validate_request: bool = True) -> None:
    request = WerkzeugOpenAPIRequest(resp.request)
    if validate_request:
        openapi.validate_request(request)
    openapi.validate_response(request, WerkzeugOpenAPIResponse(resp))


def _get(client: FlaskClient, path: str, **kwargs: object) -> TestResponse:
    return client.get(path, base_url=_BASE_URL, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/me",
        "/api/v1/clinic",
        "/api/v1/clinic/doctors",
        "/api/v1/clinic/staff",
    ],
)
def test_adr_0008_owner_responses_match_contract(openapi: OpenAPI, world: World, path: str) -> None:
    resp = _get(world.client_for(world.a.owner), path)
    assert resp.status_code == 200
    _check(openapi, resp)


def test_adr_0008_one_doctor_matches_contract(openapi: OpenAPI, world: World) -> None:
    resp = _get(world.client_for(world.a.owner), f"/api/v1/clinic/doctors/{world.a.doctor.id}")
    assert resp.status_code == 200
    _check(openapi, resp)


@pytest.mark.parametrize(
    ("path", "status"),
    [("/api/v1/clinic/staff", 403), ("/api/v1/clinic", 200)],
    ids=["perm-denied", "allowed"],
)
def test_adr_0008_front_desk_responses_match_contract(
    openapi: OpenAPI, world: World, path: str, status: int
) -> None:
    resp = _get(world.client_for(world.a.desk), path)
    assert resp.status_code == status
    _check(openapi, resp)


def test_adr_0008_clinic_required_matches_contract(openapi: OpenAPI, world: World) -> None:
    resp = _get(world.client_for(world.multi), "/api/v1/clinic")
    assert resp.status_code == 400
    _check(openapi, resp)


def test_adr_0008_not_found_matches_contract(openapi: OpenAPI, world: World) -> None:
    resp = _get(world.client_for(world.a.owner), f"/api/v1/clinic/doctors/{world.b.doctor.id}")
    assert resp.status_code == 404
    _check(openapi, resp)


def test_adr_0008_unauthenticated_me_matches_contract(openapi: OpenAPI, world: World) -> None:
    resp = _get(world.anonymous(), "/api/v1/me")
    assert resp.status_code == 401
    # A request with no session cookie does not satisfy the endpoint's security
    # scheme on purpose: only the error response is checked against the contract.
    _check(openapi, resp, validate_request=False)


def test_adr_0008_suspended_clinic_matches_contract(openapi: OpenAPI, world: World) -> None:
    resp = _get(world.client_for(world.suspended_owner), "/api/v1/clinic")
    assert resp.status_code == 403
    _check(openapi, resp)
