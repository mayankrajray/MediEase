"""Visit attachments against contracts/openapi.yaml (ADR-0008, M6d-P6).

The upload is a multipart document, which the request validator does not model, so its responses
are checked against the contract; every other route is checked in full (request and response).
"""

from __future__ import annotations

import io
from typing import Any

from flask.testing import FlaskClient
from openapi_core import OpenAPI
from werkzeug.test import TestResponse

from tests.conftest import UowFactory, World
from tests.contract.test_clinic_applications_contract import _check_response
from tests.contract.test_portal_linking_contract import _psend
from tests.contract.test_scheduling_contract import _BASE_URL, _check, _send, openapi  # noqa: F401
from tests.integration.test_appointments_http import _patient
from tests.integration.test_visits_http import _past_visit
from tests.portal_helpers import PORTAL, link_by_invite, portal_client

PDF = b"%PDF-1.7 synthetic report"


def _upload(client: FlaskClient, url: str, data: bytes = PDF) -> TestResponse:
    csrf = client.get_cookie("me_csrf", domain="localhost", path="/")
    return client.post(
        url,
        base_url=_BASE_URL,
        data={"file": (io.BytesIO(data), "report.pdf")},
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


def test_adr_0008_the_attachment_routes_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
    uow_factory: UowFactory,
) -> None:
    desk = world.client_for(world.a.desk)
    doctor = world.client_for(world.a.doctor_user)
    patient = _patient(desk)
    url = f"/api/v1/visits/{_past_visit(uow_factory, world, patient, days_ago=0)}/attachments"

    added = _expect(openapi, _upload(desk, url), 201, full=False)
    _expect(openapi, _upload(desk, url, b"not a report"), 422, full=False)
    _expect(openapi, _send(desk, "POST", url, {"file": "x"}), 415, full=False)
    second = _expect(openapi, _upload(desk, url), 201, full=False)

    _expect(openapi, _send(doctor, "GET", url), 200)
    _expect(openapi, _send(desk, "GET", url), 403)
    file = _send(doctor, "GET", f"{url}/{added['id']}/file")
    _expect(openapi, file, 200)
    one = f"{url}/{added['id']}"
    _expect(openapi, _send(doctor, "PUT", f"{one}/share", {"shared": True}), 200)
    _expect(openapi, _send(desk, "PUT", f"{one}/share", {"shared": True}), 403)
    _expect(openapi, _send(doctor, "DELETE", f"{url}/{second['id']}"), 403)
    _expect(openapi, _send(desk, "DELETE", f"{url}/{second['id']}"), 204)

    account = portal_client(world, "contract.reports@example.test")
    link_by_invite(desk, account, patient)
    listed = _expect(openapi, _psend(account, "GET", f"{PORTAL}/attachments"), 200)
    assert [i["id"] for i in listed["items"]] == [added["id"]]
    _expect(openapi, _psend(account, "GET", f"{PORTAL}/attachments/{added['id']}/file"), 200)
    _expect(openapi, _psend(account, "GET", f"{PORTAL}/attachments/{second['id']}/file"), 404)
