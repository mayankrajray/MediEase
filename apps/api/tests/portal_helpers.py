"""Helpers for M6b portal tests: signed-up portal clients, staff invites and accepted links."""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient
from sqlalchemy import Engine, text
from werkzeug.test import TestResponse

from tests.conftest import World
from tests.integration.test_portal_http import portal_csrf, sign_up

PORTAL = "/api/v1/portal"


def portal_client(world: World, email: str, name: str = "Asha Patient") -> FlaskClient:
    """A new, signed-in password account (unverified)."""
    client = world.anonymous()
    resp = sign_up(client, email=email, name=name)
    assert resp.status_code == 201, resp.get_json()
    return client


def staff_csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    assert cookie is not None
    return {"X-CSRF-Token": cookie.value}


def invite(staff: FlaskClient, patient_id: str) -> TestResponse:
    return staff.post(f"/api/v1/patients/{patient_id}/portal-invite", headers=staff_csrf(staff))


def invite_token(staff: FlaskClient, patient_id: str) -> str:
    resp = invite(staff, patient_id)
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["url"]).rsplit("/portal/link/", 1)[1]


def accept(patient: FlaskClient, token: str) -> TestResponse:
    return patient.post(f"{PORTAL}/invites/{token}/accept", headers=portal_csrf(patient))


def link_by_invite(staff: FlaskClient, patient: FlaskClient, patient_id: str) -> dict[str, Any]:
    resp = accept(patient, invite_token(staff, patient_id))
    assert resp.status_code == 201, resp.get_json()
    body: dict[str, Any] = resp.get_json()
    return body


def verify_email(db: Engine, email: str) -> None:
    """Mark a password account's email verified, as the emailed link would (M6a-P4)."""
    with db.begin() as conn:
        updated = conn.execute(
            text("UPDATE patient_accounts SET email_verified_at = now() WHERE email = :e"),
            {"e": email},
        )
        assert updated.rowcount == 1


def link_by_prescription(patient: FlaskClient, token: str, digits: str) -> TestResponse:
    return patient.post(
        f"{PORTAL}/links/prescription",
        json={"token": token, "phone_last4": digits},
        headers=portal_csrf(patient),
    )
