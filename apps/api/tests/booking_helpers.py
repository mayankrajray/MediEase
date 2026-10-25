"""Helpers for M6b-P5 tests: a verified patient asks a clinic for its first offered time, and
staff answer. Synthetic people only; times come from the clinic's own availability, so the
helpers work on any day the suite runs."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from flask.testing import FlaskClient
from sqlalchemy import create_engine
from werkzeug.test import TestResponse

from tests.conftest import Tenant, World
from tests.integration.test_portal_http import portal_csrf
from tests.portal_helpers import PORTAL, portal_client, staff_csrf, verify_email

PUBLIC = "/api/v1/public/clinics"
BLOCKS = [
    {"weekday": d, "start_time": "10:00", "end_time": "13:00", "capacity": 12, "slot_minutes": 60}
    for d in range(7)
]


def verified_client(world: World, email: str, name: str = "Asha Patient") -> FlaskClient:
    """A signed-in password account whose email is verified, as the emailed link would."""
    client = portal_client(world, email, name=name)
    engine = create_engine(world.app.config["SETTINGS"].DATABASE_URL)
    try:
        verify_email(engine, email)
    finally:
        engine.dispose()
    return client


def ensure_schedule(world: World, tenant: Tenant) -> None:
    """Every weekday 10:00-13:00 for the tenant's doctor, unless it already has hours."""
    owner = world.client_for(tenant.owner)
    url = f"/api/v1/clinic/doctors/{tenant.doctor.id}/schedule"
    if owner.get(url).get_json()["blocks"]:
        return
    resp = owner.put(url, json={"blocks": BLOCKS}, headers=staff_csrf(owner))
    assert resp.status_code == 200, resp.get_json()


def offers(world: World, tenant: Tenant) -> list[dict[str, Any]]:
    """The clinic's offered sessions for its doctor, soonest first, flattened over days."""
    resp = world.anonymous().get(
        f"{PUBLIC}/{tenant.clinic.slug}/availability?doctor_id={tenant.doctor.id}"
    )
    assert resp.status_code == 200, resp.get_json()
    return [s for day in resp.get_json()["days"] for s in day["sessions"]]


def ask(
    client: FlaskClient,
    tenant: Tenant,
    session: dict[str, Any],
    *,
    phone: str = "9000000777",
    slot: int = 0,
    **extra: Any,
) -> TestResponse:
    body: dict[str, Any] = {
        "clinic_slug": tenant.clinic.slug,
        "doctor_id": str(tenant.doctor.id),
        "session_start": session["starts_at"],
        "contact_phone": phone,
        "not_emergency_ack": True,
        **extra,
    }
    if session["slots"]:
        body["slot_start"] = session["slots"][slot]["starts_at"]
    return client.post(f"{PORTAL}/booking-requests", json=body, headers=portal_csrf(client))


def request_in(world: World, tenant: Tenant, email: str, **extra: Any) -> tuple[FlaskClient, str]:
    """A verified account's request for the clinic's first offered time; (client, request ID)."""
    ensure_schedule(world, tenant)
    client = verified_client(world, email)
    made = ask(client, tenant, offers(world, tenant)[0], **extra)
    assert made.status_code == 201, made.get_json()
    return client, str(made.get_json()["id"])


def staff_post(client: FlaskClient, url: str, body: dict[str, Any] | None = None) -> TestResponse:
    return client.post(url, json=body or {}, headers=staff_csrf(client))


def staff_session_after(
    world: World, tenant: Tenant, starts_at: str, *, nth: int = 1
) -> dict[str, Any]:
    """A staff view of an offered session after ``starts_at`` (for a proposal)."""
    later = [s for s in offers(world, tenant) if s["starts_at"] > starts_at]
    target = later[nth - 1]
    owner = world.client_for(tenant.owner)
    on_date = target["starts_at"][:10]
    listed = owner.get(f"/api/v1/sessions?date={on_date}&doctor_id={tenant.doctor.id}").get_json()
    for candidate in listed["items"]:
        if candidate["starts_at"] == target["starts_at"]:
            return dict(candidate)
    # A UTC date can differ from the clinic's: try the day before.
    prev = (date.fromisoformat(on_date) - timedelta(days=1)).isoformat()
    listed = owner.get(f"/api/v1/sessions?date={prev}&doctor_id={tenant.doctor.id}").get_json()
    return dict(next(c for c in listed["items"] if c["starts_at"] == target["starts_at"]))


def propose(
    world: World, tenant: Tenant, request_id: str, starts_at: str, **record: Any
) -> TestResponse:
    """Staff propose the next offered session after ``starts_at`` (its first slot)."""
    target = staff_session_after(world, tenant, starts_at)
    chosen = record or {"new_patient": {"sex": "FEMALE", "age_years": 30}}
    body: dict[str, Any] = {"session_id": target["id"], **chosen}
    if target["slots"]:
        body["slot_start"] = target["slots"][0]["starts_at"]
    return staff_post(
        world.client_for(tenant.desk), f"/api/v1/booking-requests/{request_id}/propose", body
    )
