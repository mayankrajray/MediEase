"""Clinic applications against contracts/openapi.yaml (M6c-P1, ADR-0008).

The multipart submission's responses are checked against the contract; its request body is a
multipart document, which the request validator does not model, so the JSON part's schema is
checked against ``ClinicApplicationInput`` directly. Confirming and the ops list are checked in
full (request and response).
"""

from __future__ import annotations

import json

from openapi_core import OpenAPI
from openapi_core.contrib.werkzeug import WerkzeugOpenAPIRequest, WerkzeugOpenAPIResponse
from sqlalchemy import create_engine
from werkzeug.test import EnvironBuilder, TestResponse
from werkzeug.wrappers import Request

from tests.conftest import UowFactory, World, make_db_app
from tests.contract.test_scheduling_contract import _BASE_URL, _check, _send, openapi  # noqa: F401
from tests.integration.test_clinic_applications_http import (
    MemoryStore,
    _confirm_token,
    solo_body,
    submit,
)


def _check_response(openapi: OpenAPI, resp: TestResponse) -> None:  # noqa: F811
    request = WerkzeugOpenAPIRequest(
        Request(
            EnvironBuilder(
                base_url=_BASE_URL, path=resp.request.path, method=resp.request.method
            ).get_environ()
        )
    )
    openapi.validate_response(request, WerkzeugOpenAPIResponse(resp))


def test_adr_0008_applying_and_its_errors_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    migrated_database_url: str,
    uow_factory: UowFactory,
    world: World,
) -> None:
    schema = openapi.spec / "components" / "schemas" / "ClinicApplicationInput"
    properties = set((schema / "properties").keys())
    assert set(solo_body()) | {"website"} == properties

    anon = make_db_app(migrated_database_url, blob_storage=MemoryStore()).test_client()
    for resp, status in (
        (submit(anon, solo_body()), 202),
        (submit(anon, solo_body(), {1: b"text"}), 422),
        (submit(anon, solo_body(pincode="011001")), 422),
        (anon.post("/api/v1/public/applications", json=solo_body()), 415),
    ):
        assert resp.status_code == status, resp.get_json()
        _check_response(openapi, resp)

    engine = create_engine(migrated_database_url)
    try:
        token = _confirm_token(engine, uow_factory)
    finally:
        engine.dispose()
    confirmed = _send(anon, "POST", "/api/v1/public/applications/confirm", {"token": token})
    assert confirmed.status_code == 200
    _check(openapi, confirmed)
    again = _send(anon, "POST", "/api/v1/public/applications/confirm", {"token": token})
    assert again.status_code == 404
    _check(openapi, again)

    ops = world.client_for(world.ops)
    listed = _send(ops, "GET", "/api/v1/ops/applications")
    assert listed.status_code == 200 and len(listed.get_json()["items"]) == 1
    _check(openapi, listed)
    assert "owner_email" not in json.dumps(listed.get_json())
