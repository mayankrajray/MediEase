"""Contract tests for the auth endpoints (ADR-0008, M1-P2).

Real responses from the app wired to PostgreSQL are validated against
contracts/openapi.yaml: status, headers and body schema, success and error.
"""

from __future__ import annotations

from json import dumps
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from openapi_core import OpenAPI
from openapi_core.contrib.werkzeug import WerkzeugOpenAPIRequest, WerkzeugOpenAPIResponse
from werkzeug.test import EnvironBuilder, TestResponse
from werkzeug.wrappers import Request

from tests.conftest import DEMO_PASSWORD, UowFactory, seed_staff

_SPEC_PATH = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
_BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def openapi() -> OpenAPI:
    return OpenAPI.from_file_path(str(_SPEC_PATH))


def _check(openapi: OpenAPI, resp: TestResponse, *, validate_request: bool = True) -> None:
    sent = resp.request
    # The app already consumed the body stream; rebuild the request for validation.
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


def _post(client: FlaskClient, path: str, json: object = None, **kwargs: object) -> TestResponse:
    resp = client.post(path, base_url=_BASE_URL, json=json, **kwargs)  # type: ignore[arg-type]
    resp.sent_body = b"" if json is None else dumps(json).encode()  # type: ignore[attr-defined]
    return resp


def _csrf(client: FlaskClient) -> dict[str, str]:
    # Re-read every time: sign-in and refresh rotate the me_csrf cookie.
    csrf = client.get_cookie("me_csrf", domain="localhost", path="/")
    assert csrf is not None
    return {"X-CSRF-Token": csrf.value}


def _signed_in(client: FlaskClient, uow_factory: UowFactory) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    resp = _post(
        client,
        "/api/v1/auth/sign-in",
        json={"identifier": user.email.value, "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200


def test_adr_0008_sign_in_200_matches_contract(
    openapi: OpenAPI, db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    resp = _post(
        db_client,
        "/api/v1/auth/sign-in",
        json={"identifier": user.email.value, "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200
    _check(openapi, resp)


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"identifier": "nobody@example.test", "password": "x"}, 401),
        ({"identifier": "nobody@example.test"}, 422),
    ],
)
def test_adr_0008_sign_in_errors_match_contract(
    openapi: OpenAPI, db_client: FlaskClient, body: dict[str, str], status: int
) -> None:
    resp = _post(db_client, "/api/v1/auth/sign-in", json=body)
    assert resp.status_code == status
    # A deliberately invalid request is not checked against the request schema.
    _check(openapi, resp, validate_request=status != 422)


def test_adr_0008_sign_in_423_matches_contract(
    openapi: OpenAPI, db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    user = seed_staff(uow_factory)
    assert user.email is not None
    body = {"identifier": user.email.value, "password": "not-the-password"}
    for _ in range(5):
        _post(db_client, "/api/v1/auth/sign-in", json=body)
    resp = _post(db_client, "/api/v1/auth/sign-in", json=body)
    assert resp.status_code == 423
    _check(openapi, resp)


def test_adr_0008_refresh_and_sign_out_match_contract(
    openapi: OpenAPI, db_client: FlaskClient, uow_factory: UowFactory
) -> None:
    _signed_in(db_client, uow_factory)
    refreshed = _post(db_client, "/api/v1/auth/refresh", headers=_csrf(db_client))
    assert refreshed.status_code == 200
    _check(openapi, refreshed)

    forbidden = _post(db_client, "/api/v1/auth/sign-out")
    assert forbidden.status_code == 403
    _check(openapi, forbidden)

    signed_out = _post(db_client, "/api/v1/auth/sign-out", headers=_csrf(db_client))
    assert signed_out.status_code == 204
    _check(openapi, signed_out)

    expired = _post(db_client, "/api/v1/auth/refresh")
    assert expired.status_code == 401
    _check(openapi, expired)
