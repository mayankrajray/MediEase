"""Contract tests for the portal and Google sign-in (ADR-0008, M6a-P3)."""

from __future__ import annotations

from urllib.parse import urlencode

from flask.testing import FlaskClient
from openapi_core import OpenAPI
from openapi_core.contrib.werkzeug import WerkzeugOpenAPIRequest, WerkzeugOpenAPIResponse
from werkzeug.test import EnvironBuilder, TestResponse
from werkzeug.wrappers import Request

from tests.contract.test_auth_contract import _BASE_URL, _check, _post, openapi  # noqa: F401
from tests.integration.test_portal_http import EMAIL, PASSWORD

SIGN_UP = "/api/v1/portal/auth/sign-up"
BODY = {"full_name": "Asha Patient", "email": EMAIL, "password": PASSWORD}


def _check_get(spec: OpenAPI, resp: TestResponse) -> None:
    """``_check`` for a GET whose query string matters (the shared helper drops it)."""
    sent = resp.request
    request = WerkzeugOpenAPIRequest(
        Request(
            EnvironBuilder(
                base_url=_BASE_URL,
                path=sent.path,
                method="GET",
                query_string=sent.query_string.decode(),
                headers=dict(sent.headers),
            ).get_environ()
        )
    )
    spec.validate_request(request)
    spec.validate_response(request, WerkzeugOpenAPIResponse(resp))


def _portal_csrf(client: FlaskClient) -> dict[str, str]:
    csrf = client.get_cookie("me_pt_csrf", domain="localhost", path="/")
    assert csrf is not None
    return {"X-CSRF-Token": csrf.value}


def test_adr_0008_portal_sign_up_sign_in_me_refresh_sign_out_match_contract(
    openapi: OpenAPI,  # noqa: F811
    db_client: FlaskClient,
) -> None:
    created = _post(db_client, SIGN_UP, json=BODY)
    assert created.status_code == 201
    _check(openapi, created)

    taken = _post(db_client.application.test_client(), SIGN_UP, json=BODY)
    assert taken.status_code == 409
    _check(openapi, taken)

    signed_in = _post(
        db_client, "/api/v1/portal/auth/sign-in", json={"email": EMAIL, "password": PASSWORD}
    )
    assert signed_in.status_code == 200
    _check(openapi, signed_in)

    wrong = _post(
        db_client.application.test_client(),
        "/api/v1/portal/auth/sign-in",
        json={"email": EMAIL, "password": "not-the-password"},
    )
    assert wrong.status_code == 401
    _check(openapi, wrong)

    me = db_client.get("/api/v1/portal/me", base_url=_BASE_URL)
    assert me.status_code == 200
    _check(openapi, me)

    refreshed = _post(db_client, "/api/v1/portal/auth/refresh", headers=_portal_csrf(db_client))
    assert refreshed.status_code == 200
    _check(openapi, refreshed)

    out = _post(db_client, "/api/v1/portal/auth/sign-out", headers=_portal_csrf(db_client))
    assert out.status_code == 204
    _check(openapi, out)

    gone = db_client.get("/api/v1/portal/me", base_url=_BASE_URL)
    assert gone.status_code == 401
    # No cookie any more, so the request itself no longer meets the security requirement.
    _check(openapi, gone, validate_request=False)


def test_adr_0008_google_start_and_callback_redirects_match_contract(
    openapi: OpenAPI,  # noqa: F811
    db_client: FlaskClient,
) -> None:
    query = urlencode({"intent": "patient", "login_hint": "g@example.test", "next": "/portal"})
    started = db_client.get(f"/api/v1/auth/google/start?{query}", base_url=_BASE_URL)
    assert started.status_code == 302
    _check_get(openapi, started)

    finished = db_client.get(started.headers["Location"], base_url=_BASE_URL)
    assert finished.status_code == 302
    assert finished.headers["Location"] == "/portal"
    _check_get(openapi, finished)
