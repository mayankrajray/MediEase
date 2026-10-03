"""Tenancy isolation over HTTP (NFR-08, spec R8, AC3).

The repository suite proves clinic A's scope cannot reach clinic B's rows.
This one proves the same through the whole stack, for the requests a browser
actually makes, and keeps itself honest: ``test_every_clinic_route_with_an_id``
fails when a new clinic endpoint takes a resource ID without a cross-clinic
case here, so the guard cannot be forgotten (CLAUDE.md "Tenancy isolation is a
permanent test suite").
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from flask.testing import FlaskClient
from werkzeug.test import TestResponse

from mediease_api.delivery.http.access import Access, policy_of
from tests.conftest import World

# Rule -> a URL naming a resource of clinic B. Requested by clinic A's owner,
# each must answer 404 as if it did not exist.
CROSS_TENANT_CASES: dict[str, Callable[[World], str]] = {
    "/api/v1/clinic/doctors/<uuid:doctor_id>": lambda w: f"/api/v1/clinic/doctors/{w.b.doctor.id}",
    "/api/v1/clinic/staff/<uuid:membership_id>": lambda w: _staff_url(w),
    "/api/v1/patients/<uuid:patient_id>": lambda w: _patient_url(w),
}

# Methods a cross-tenant case must use (default GET), with the body to send.
CROSS_TENANT_WRITES: dict[str, tuple[str, dict[str, str]]] = {
    "/api/v1/clinic/staff/<uuid:membership_id>": ("PATCH", {"role": "DOCTOR"}),
}

# Patients have their own read and write cross-clinic cases in integration/test_patients_http.py;
# this suite reads one by ID so the "every route with an ID" guard below stays complete.


def _staff_url(world: World) -> str:
    """Clinic B's front-desk membership, which clinic A must not be able to reach."""
    owner_of_b = world.client_for(world.b.owner)
    staff = owner_of_b.get("/api/v1/clinic/staff").get_json()["items"]
    membership_id = next(m["membership_id"] for m in staff if m["full_name"] == "Beta Front_Desk")
    return f"/api/v1/clinic/staff/{membership_id}"


def _patient_url(world: World) -> str:
    """A patient of clinic B, registered by B's owner, which clinic A must not be able to reach."""
    owner_of_b = world.client_for(world.b.owner)
    csrf = owner_of_b.get_cookie("me_csrf", path="/")
    assert csrf is not None
    created = owner_of_b.post(
        "/api/v1/patients",
        json={
            "full_name": "Beta Patient",
            "phone": "9000000042",
            "sex": "UNDISCLOSED",
            "date_of_birth": "1990-05-17",
        },
        headers={"X-CSRF-Token": csrf.value},
    )
    assert created.status_code == 201, created.get_json()
    return f"/api/v1/patients/{created.get_json()['id']}"


def _clinic_rules_with_an_id(world: World) -> set[str]:
    return {
        rule.rule
        for rule in world.app.url_map.iter_rules()
        if "<" in rule.rule
        and (policy := policy_of(world.app.view_functions[rule.endpoint])) is not None
        and policy.access is Access.CLINIC
    }


def test_nfr_08_every_clinic_route_with_an_id_has_a_cross_tenant_case(world: World) -> None:
    assert _clinic_rules_with_an_id(world) == set(CROSS_TENANT_CASES)


@pytest.mark.parametrize("rule", sorted(CROSS_TENANT_CASES))
def test_ac3_nfr_08_another_clinics_resource_is_404(world: World, rule: str) -> None:
    url = CROSS_TENANT_CASES[rule](world)
    owner_of_a = world.client_for(world.a.owner)
    method, body = CROSS_TENANT_WRITES.get(rule, ("GET", {}))

    resp = _call(owner_of_a, method, url, body)
    assert resp.status_code == 404, resp.get_json()
    assert resp.get_json()["error"]["code"] == "REQ_NOT_FOUND"
    # The same URL works for its own clinic, so the 404 is the scope, not the route.
    assert _call(world.client_for(world.b.owner), method, url, body).status_code == 200


def _call(client: FlaskClient, method: str, url: str, body: dict[str, str]) -> TestResponse:
    if method == "GET":
        return client.get(url)
    csrf = client.get_cookie("me_csrf", path="/")
    assert csrf is not None
    return client.open(url, method=method, json=body, headers={"X-CSRF-Token": csrf.value})


def test_ac3_nfr_08_no_other_clinics_rows_appear_in_any_list(world: World) -> None:
    owner_of_a = world.client_for(world.a.owner)

    doctors = owner_of_a.get("/api/v1/clinic/doctors").get_json()["items"]
    assert [d["id"] for d in doctors] == [str(world.a.doctor.id)]
    assert str(world.b.doctor.id) not in owner_of_a.get("/api/v1/clinic/doctors").text

    staff = owner_of_a.get("/api/v1/clinic/staff").get_json()["items"]
    assert str(world.b.owner.id) not in {m["user_id"] for m in staff}
    assert all(name.startswith(("Alpha", "Multi")) for name in (m["full_name"] for m in staff))


def test_ac3_nfr_08_the_clinic_endpoint_never_returns_another_clinic(world: World) -> None:
    body = world.client_for(world.a.owner).get("/api/v1/clinic").get_json()
    assert body["id"] == str(world.a.clinic.id)
    assert body["name"] == "Alpha Sample Clinic"


def test_r8_a_cross_clinic_read_is_logged_as_tenancy_not_found(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    client = world.client_for(world.a.owner)
    capsys.readouterr()
    client.get(f"/api/v1/clinic/doctors/{world.b.doctor.id}")
    out = capsys.readouterr().out
    assert "tenancy.not_found" in out
    assert str(world.a.clinic.id) in out  # the scope that refused, for monitoring
