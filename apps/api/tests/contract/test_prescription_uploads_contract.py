"""Verified prescription uploads against contracts/openapi.yaml (ADR-0008, M7b).

The file upload is multipart, which the request validator does not model, so its responses are
checked against the contract; every other route is checked in full (request and response).
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest
from flask.testing import FlaskClient
from openapi_core import OpenAPI
from sqlalchemy import Engine, create_engine
from werkzeug.test import TestResponse

from tests.booking_helpers import verified_client
from tests.conftest import UowFactory, World, make_db_app
from tests.contract.test_clinic_applications_contract import _check_response
from tests.contract.test_portal_linking_contract import _psend
from tests.contract.test_scheduling_contract import _BASE_URL, _check, openapi  # noqa: F401
from tests.integration.test_clinic_applications_http import MemoryStore
from tests.integration.test_patient_links_http import _last4, _link, _wrong
from tests.integration.test_prescriptions_http import _issued
from tests.portal_helpers import link_by_invite, portal_client
from tests.upload_helpers import UPL, process


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _upload(client: FlaskClient, data: bytes) -> TestResponse:
    csrf = client.get_cookie("me_pt_csrf", domain="localhost", path="/")
    return client.post(
        UPL,
        base_url=_BASE_URL,
        data={"file": (io.BytesIO(data), "rx.pdf")},
        content_type="multipart/form-data",
        headers={"X-CSRF-Token": csrf.value} if csrf else {},
    )


def _expect(openapi: OpenAPI, resp: TestResponse, status: int, *, full: bool = True) -> Any:  # noqa: F811
    assert resp.status_code == status, resp.get_json()
    if full:
        _check(openapi, resp)
    else:
        _check_response(openapi, resp)
    return resp.get_json() if resp.mimetype == "application/json" else None


def test_adr_0008_the_upload_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
    db: Engine,
    uow_factory: UowFactory,
) -> None:
    store = MemoryStore()
    url = world.app.config["SETTINGS"].DATABASE_URL
    w = replace(world, app=make_db_app(url, blob_storage=store))
    _, visit, rx = _issued(w)
    _link(w, rx["id"])
    patient = portal_client(w, "contract.uploads@example.test")
    link_by_invite(w.client_for(w.a.owner), patient, visit["patient_id"])

    pdf = w.client_for(w.a.doctor_user).get(f"/api/v1/prescriptions/{rx['id']}/pdf").data
    accepted = _expect(openapi, _upload(patient, pdf), 202, full=False)
    one = f"{UPL}/{accepted['id']}"
    _expect(openapi, _psend(patient, "GET", one), 200)
    process(db, uow_factory, store)
    assert _expect(openapi, _psend(patient, "GET", one), 200)["state"] == "VERIFIED"
    _expect(openapi, _upload(patient, b"GIF89a" + b"0" * 32), 422, full=False)
    _expect(openapi, _psend(patient, "GET", f"{UPL}/{UUID(int=1)}"), 404)

    typed = _expect(openapi, _psend(patient, "POST", f"{UPL}/by-code", {"code": rx["id"]}), 201)
    mine = f"{UPL}/{typed['id']}"
    _expect(openapi, _psend(patient, "POST", f"{UPL}/by-code", {"code": "nope"}), 422)
    _expect(openapi, _psend(patient, "POST", f"{mine}/selection", {"choice": "LATEST"}), 200)
    # An unverified account cannot answer a check at all.
    _expect(openapi, _psend(patient, "POST", f"{mine}/challenge", {"phone_last4": "1234"}), 403)
    _expect(openapi, _psend(patient, "DELETE", mine), 204)

    rep = verified_client(w, "contract.representative@example.test")
    pending = _expect(openapi, _psend(rep, "POST", f"{UPL}/by-code", {"code": rx["id"]}), 201)
    theirs = f"{UPL}/{pending['id']}"
    right = _last4(w, visit["patient_id"])
    _expect(
        openapi, _psend(rep, "POST", f"{theirs}/challenge", {"phone_last4": _wrong(right)}), 401
    )
    _expect(openapi, _psend(rep, "POST", f"{theirs}/selection", {"choice": "UPLOADED"}), 409)
    _expect(openapi, _psend(rep, "POST", f"{theirs}/challenge", {"phone_last4": right}), 200)
