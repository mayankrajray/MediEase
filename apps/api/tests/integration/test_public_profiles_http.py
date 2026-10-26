"""Public profiles, indexing and the sitemap over HTTP (M6c-P5; FR-DIS-03, 06, 07; spec R59-R64).

Real PostgreSQL. The world's clinics are verified, their doctors verified and shown.
"""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient

from tests.booking_helpers import ensure_schedule
from tests.conftest import Tenant, World
from tests.portal_helpers import staff_csrf

LISTING = "/api/v1/clinic/listing"
PUBLIC = "/api/v1/public/clinics"


def _put(client: FlaskClient, url: str, body: dict[str, Any]) -> Any:
    return client.put(url, json=body, headers=staff_csrf(client))


def _make_discoverable(world: World, tenant: Tenant) -> FlaskClient:
    owner = world.client_for(tenant.owner)
    ensure_schedule(world, tenant)
    owner.patch(
        "/api/v1/clinic",
        json={"address_line": "1 Sample Road", "city": "Sample City", "pincode": "560001"},
        headers=staff_csrf(owner),
    )
    listed = _put(owner, LISTING, {"listed": True})
    assert listed.status_code == 200 and listed.get_json()["discoverable"], listed.get_json()
    return owner


def test_r59_r61_the_profile_shows_only_shown_doctors_with_their_languages_and_fee(
    world: World,
) -> None:
    owner = world.client_for(world.a.owner)
    url = f"{LISTING}/doctors/{world.a.doctor.id}/profile"
    bad = _put(owner, url, {"languages": ["Klingon"]})
    assert bad.status_code == 422
    # M6d-P1 (D8): the fee is the consultation price on the fee schedule, shown on request.
    fees = owner.post(
        "/api/v1/clinic/fees/services",
        json={"name": "Consultation", "kind": "CONSULTATION", "default_price_paise": 50000},
        headers=staff_csrf(owner),
    )
    assert fees.status_code == 201, fees.get_json()
    hidden_fee = _put(owner, url, {"languages": ["Hindi", "English"]}).get_json()
    assert hidden_fee["doctors"][0]["fee_paise"] == 50000
    assert hidden_fee["doctors"][0]["show_fee"] is False
    page = world.anonymous().get(f"{PUBLIC}/{world.a.clinic.slug}").get_json()
    assert page["doctors"][0]["fee_paise"] is None
    saved = _put(owner, url, {"show_fee": True}).get_json()
    assert saved["doctors"][0]["languages"] == ["Hindi", "English"]
    assert saved["doctors"][0]["show_fee"] is True
    assert _put(owner, url, {"fee_paise": 1}).status_code == 422  # no longer set here
    assert "Hindi" in saved["language_options"]

    anon = world.anonymous()
    page = anon.get(f"{PUBLIC}/{world.a.clinic.slug}").get_json()
    [doctor] = page["doctors"]
    assert (doctor["languages"], doctor["fee_paise"]) == (["Hindi", "English"], 50000)
    assert page["indexable"] is False  # R62: not listed, so not indexable

    _put(owner, f"{LISTING}/doctors/{world.a.doctor.id}", {"visible": False})
    assert anon.get(f"{PUBLIC}/{world.a.clinic.slug}").get_json()["doctors"] == []
    hidden = anon.get(f"{PUBLIC}/{world.a.clinic.slug}/availability?doctor_id={world.a.doctor.id}")
    assert hidden.status_code == 404  # R59: one answer for hidden and unknown doctors


def test_r62_r63_a_discoverable_clinic_is_indexable_and_in_the_sitemap_until_it_opts_out(
    world: World,
) -> None:
    owner = _make_discoverable(world, world.a)
    anon = world.anonymous()
    assert anon.get(f"{PUBLIC}/{world.a.clinic.slug}").get_json()["indexable"] is True
    sitemap = anon.get("/api/v1/public/sitemap")
    assert sitemap.status_code == 200
    locs = [i["loc"] for i in sitemap.get_json()["items"]]
    assert any(loc.endswith(f"/c/{world.a.clinic.slug}") for loc in locs)
    assert any(loc.endswith(f"/doctors/{world.a.doctor.id}") for loc in locs)
    assert not any(world.b.clinic.slug in loc for loc in locs)  # not listed

    opted_out = _put(owner, LISTING, {"search_indexing": False}).get_json()
    assert opted_out["search_indexing"] is False and opted_out["listed"] is True
    assert anon.get(f"{PUBLIC}/{world.a.clinic.slug}").get_json()["indexable"] is False
    locs = [i["loc"] for i in anon.get("/api/v1/public/sitemap").get_json()["items"]]
    assert not any(world.a.clinic.slug in loc for loc in locs)
    assert _put(owner, LISTING, {}).status_code == 422


def test_r59_a_request_for_a_hidden_doctor_is_refused(world: World) -> None:
    from tests.booking_helpers import ask, offers, verified_client

    ensure_schedule(world, world.a)
    session = offers(world, world.a)[0]
    owner = world.client_for(world.a.owner)
    _put(owner, f"{LISTING}/doctors/{world.a.doctor.id}", {"visible": False})
    patient = verified_client(world, "hidden.doctor@example.test")
    resp = ask(patient, world.a, session)
    assert resp.status_code == 409, resp.get_json()
