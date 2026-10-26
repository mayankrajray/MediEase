"""Directory search over HTTP (M6c-P6; FR-DIS-01, 02, 04, 05; spec discovery R1-R10).

Real PostgreSQL with pg_trgm. Clinic A is made discoverable; clinic B stays unlisted.
"""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient

from mediease_api.delivery.http.public_search import (
    CLINIC_HIT_DOCTOR_FIELDS,
    CLINIC_HIT_FIELDS,
    DOCTOR_HIT_CLINIC_FIELDS,
    DOCTOR_HIT_FIELDS,
)
from tests.booking_helpers import ensure_schedule
from tests.conftest import World
from tests.portal_helpers import staff_csrf

SEARCH = "/api/v1/public/search"
LISTING = "/api/v1/clinic/listing"


def _discoverable_a(world: World) -> FlaskClient:
    owner = world.client_for(world.a.owner)
    ensure_schedule(world, world.a)
    resp = owner.patch(
        "/api/v1/clinic",
        json={
            "address_line": "1 Sample Road",
            "city": "Sample City",
            "state": "Karnataka",
            "pincode": "560001",
            "specialties": ["General Medicine"],
        },
        headers=staff_csrf(owner),
    )
    assert resp.status_code == 200, resp.get_json()
    owner.put(
        f"{LISTING}/doctors/{world.a.doctor.id}/profile",
        json={"languages": ["Hindi", "English"], "fee_paise": 40000},
        headers=staff_csrf(owner),
    )
    listed = owner.put(LISTING, json={"listed": True}, headers=staff_csrf(owner))
    assert listed.get_json()["discoverable"] is True, listed.get_json()
    return owner


def _items(client: FlaskClient, kind: str, **query: str) -> list[dict[str, Any]]:
    resp = client.get(f"{SEARCH}/{kind}", query_string=query)
    assert resp.status_code == 200, resp.get_json()
    assert resp.headers["Cache-Control"] == "no-store"
    return list(resp.get_json()["items"])


def test_ac18_only_discoverable_clinics_are_found_by_name_doctor_or_specialty(
    world: World,
) -> None:
    _discoverable_a(world)
    anon = world.anonymous()
    everything = _items(anon, "clinics")
    assert [c["slug"] for c in everything] == [world.a.clinic.slug]  # B is not listed
    [hit] = _items(anon, "clinics", q="alpha sample")
    assert set(hit) == CLINIC_HIT_FIELDS and set(hit["doctors"][0]) == CLINIC_HIT_DOCTOR_FIELDS
    assert hit["next_available"] is not None
    assert _items(anon, "clinics", q="dr alpha")[0]["slug"] == world.a.clinic.slug
    assert _items(anon, "clinics", q="general medicine")[0]["slug"] == world.a.clinic.slug
    assert _items(anon, "clinics", q="zzzz qqqq") == []

    [doctor] = _items(anon, "doctors", q="alpha", language="Hindi")
    assert set(doctor) == DOCTOR_HIT_FIELDS and set(doctor["clinic"]) == DOCTOR_HIT_CLINIC_FIELDS
    assert (doctor["id"], doctor["fee_paise"]) == (str(world.a.doctor.id), 40000)
    assert _items(anon, "doctors", language="Tamil") == []


def test_r3_place_filters_by_pin_city_and_pin_district(world: World) -> None:
    _discoverable_a(world)
    anon = world.anonymous()
    assert len(_items(anon, "clinics", pincode="560001")) == 1
    assert len(_items(anon, "clinics", pincode="560099")) == 1  # the same PIN district
    assert len(_items(anon, "clinics", city="sample city")) == 1
    assert _items(anon, "clinics", pincode="110001") == []
    assert _items(anon, "doctors", city="Elsewhere") == []


def test_r4_available_needs_a_free_time_in_seven_days(world: World) -> None:
    owner = _discoverable_a(world)
    anon = world.anonymous()
    assert len(_items(anon, "doctors", available="true")) == 1
    # Without weekly hours the clinic is no longer discoverable at all (R55).
    blocks = owner.put(
        f"/api/v1/clinic/doctors/{world.a.doctor.id}/schedule",
        json={"blocks": []},
        headers=staff_csrf(owner),
    )
    assert blocks.status_code == 200, blocks.get_json()
    assert _items(anon, "clinics") == []


def test_r6_suspended_hidden_and_unlisted_are_never_found(world: World) -> None:
    owner = _discoverable_a(world)
    anon = world.anonymous()
    owner.put(
        f"{LISTING}/doctors/{world.a.doctor.id}", json={"visible": False}, headers=staff_csrf(owner)
    )
    assert _items(anon, "doctors") == [] and _items(anon, "clinics") == []
    owner.put(
        f"{LISTING}/doctors/{world.a.doctor.id}", json={"visible": True}, headers=staff_csrf(owner)
    )
    admin = world.client_for(world.ops)
    admin.post(
        f"/api/v1/ops/clinics/{world.a.clinic.id}/suspend",
        json={"reason": "PAYMENT"},
        headers=staff_csrf(admin),
    )
    assert _items(anon, "clinics") == [] and _items(anon, "doctors") == []


def test_r1_bad_filters_are_named(world: World) -> None:
    anon = world.anonymous()
    for query, field in (
        ({"pincode": "12345"}, "pincode"),
        ({"language": "Klingon"}, "language"),
        ({"available": "maybe"}, "available"),
        ({"q": "x" * 101}, "q"),
    ):
        resp = anon.get(f"{SEARCH}/clinics", query_string=query)
        assert resp.status_code == 422, query
        assert resp.get_json()["error"]["details"]["fields"][0]["field"] == field
    options = anon.get(f"{SEARCH}/doctors").get_json()["options"]
    assert "Hindi" in options["languages"] and options["specialties"]
