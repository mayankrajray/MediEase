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

from mediease_api.delivery.http.access import Access, policy_of
from tests.conftest import World

# Rule -> a URL naming a resource of clinic B. Requested by clinic A's owner,
# each must answer 404 as if it did not exist.
CROSS_TENANT_CASES: dict[str, Callable[[World], str]] = {
    "/api/v1/clinic/doctors/<uuid:doctor_id>": lambda w: f"/api/v1/clinic/doctors/{w.b.doctor.id}",
}


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

    resp = owner_of_a.get(url)
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "REQ_NOT_FOUND"
    # The same URL works for its own clinic, so the 404 is the scope, not the route.
    assert world.client_for(world.b.owner).get(url).status_code == 200


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
