"""Integration tests for /health and request correlation (NFR-12).

Acceptance criteria from docs/milestones/M0-foundation.md: 200 with
{"status":"ok"}, an X-Request-ID response header on every request, and an
inbound X-Request-ID echoed back unchanged.
"""

from __future__ import annotations

import pytest
from flask.testing import FlaskClient
from ulid import ULID


def test_nfr_12_health_returns_200_ok(client: FlaskClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_nfr_12_health_generates_ulid_request_id(client: FlaskClient) -> None:
    resp = client.get("/health")
    ULID.from_str(resp.headers["X-Request-ID"])  # raises if not a valid ULID


def test_nfr_12_health_echoes_inbound_request_id(client: FlaskClient) -> None:
    resp = client.get("/health", headers={"X-Request-ID": "test-123"})
    assert resp.headers["X-Request-ID"] == "test-123"


@pytest.mark.parametrize(
    "inbound",
    ["x" * 65, "has space", 'quote"inside', ""],
    ids=["too-long", "space", "quote", "empty"],
)
def test_nfr_12_unsafe_request_id_is_replaced(client: FlaskClient, inbound: str) -> None:
    resp = client.get("/health", headers={"X-Request-ID": inbound})
    returned = resp.headers["X-Request-ID"]
    assert returned != inbound
    ULID.from_str(returned)


def test_nfr_12_request_id_at_max_length_is_kept(client: FlaskClient) -> None:
    inbound = "a" * 64
    resp = client.get("/health", headers={"X-Request-ID": inbound})
    assert resp.headers["X-Request-ID"] == inbound
