"""Contract tests: real responses match contracts/openapi.yaml (ADR-0008).

The contract is the source of truth for the web client's generated types, so a
response that drifts from it is a bug even if every other test passes. Each
case validates the request and the response (status, headers, body schema)
with openapi-core.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from flask.testing import FlaskClient
from openapi_core import OpenAPI
from openapi_core.contrib.werkzeug import WerkzeugOpenAPIRequest, WerkzeugOpenAPIResponse
from openapi_core.validation.response.exceptions import InvalidData
from werkzeug.test import TestResponse

from mediease_api.ports.readiness import DatabaseTimeout, DatabaseUnavailable, ReadinessError
from tests.conftest import FakeDatabaseCheck

_SPEC_PATH = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
# Must match a `servers` entry in the contract so paths resolve.
_BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    return OpenAPI.from_file_path(str(_SPEC_PATH))


def _assert_matches_contract(openapi: OpenAPI, resp: TestResponse) -> None:
    request = WerkzeugOpenAPIRequest(resp.request)
    openapi.validate_request(request)
    openapi.validate_response(request, WerkzeugOpenAPIResponse(resp))


def test_adr_0008_health_matches_contract(openapi: OpenAPI, client: FlaskClient) -> None:
    resp = client.get("/health", base_url=_BASE_URL, headers={"X-Request-ID": "contract-1"})
    assert resp.status_code == 200
    _assert_matches_contract(openapi, resp)


def test_adr_0008_ready_200_matches_contract(openapi: OpenAPI, client: FlaskClient) -> None:
    resp = client.get("/ready", base_url=_BASE_URL)
    assert resp.status_code == 200
    _assert_matches_contract(openapi, resp)


@pytest.mark.parametrize(
    "error", [DatabaseUnavailable(), DatabaseTimeout()], ids=["unavailable", "timeout"]
)
def test_adr_0008_ready_503_matches_contract(
    openapi: OpenAPI,
    client: FlaskClient,
    database_check: FakeDatabaseCheck,
    error: ReadinessError,
) -> None:
    database_check.error = error
    resp = client.get("/ready", base_url=_BASE_URL)
    assert resp.status_code == 503
    _assert_matches_contract(openapi, resp)


def test_adr_0008_contract_rejects_a_drifted_response(
    openapi: OpenAPI, client: FlaskClient
) -> None:
    """Guard the guard: a body that breaks the schema must fail validation."""
    resp = client.get("/health", base_url=_BASE_URL)
    resp.set_data(b'{"status": "degraded"}')
    with pytest.raises(InvalidData):
        _assert_matches_contract(openapi, resp)
