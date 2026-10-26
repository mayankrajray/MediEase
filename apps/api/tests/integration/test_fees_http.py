"""The fee schedule over HTTP (M6d-P1; FR-BIL-01; spec billing R1-R12, AC1-AC3).

Real PostgreSQL. The test world's clinics are built through repositories, so they start without
services; a clinic made through ``CreateClinic`` gets the starting pair (R2).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from tests.conftest import World
from tests.portal_helpers import staff_csrf

FEES = "/api/v1/clinic/fees"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _send(client: FlaskClient, method: str, url: str, body: dict[str, Any]) -> Any:
    return client.open(url, method=method, json=body, headers=staff_csrf(client))


def _service(schedule: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in schedule["services"] if s["name"] == name)


def test_ac1_r2_a_new_clinic_starts_with_consultation_and_follow_up(
    world: World, db: Engine
) -> None:
    ops = world.client_for(world.ops)
    made = ops.post(
        "/api/v1/ops/clinics",
        json={"name": "Sample Fees Clinic", "slug": "sample-fees-clinic"},
        headers=staff_csrf(ops),
    )
    assert made.status_code == 201, made.get_json()
    with db.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT s.name, s.kind, s.default_price_paise FROM clinic_services s"
                " JOIN clinics c ON c.id = s.clinic_id WHERE c.slug = 'sample-fees-clinic'"
                " ORDER BY s.position"
            )
        ).all()
    assert [tuple(r) for r in rows] == [
        ("Consultation", "CONSULTATION", None),
        ("Follow-up", "FOLLOW_UP", None),
    ]


def test_ac2_the_owner_prices_services_and_doctors_and_every_change_is_audited(
    world: World, db: Engine
) -> None:
    owner = world.client_for(world.a.owner)
    added = _send(
        owner,
        "POST",
        f"{FEES}/services",
        {"name": "Consultation", "kind": "CONSULTATION", "default_price_paise": 50000},
    )
    assert added.status_code == 201, added.get_json()
    dressing = _send(
        owner, "POST", f"{FEES}/services", {"name": "Dressing", "kind": "PROCEDURE"}
    ).get_json()
    service = _service(dressing, "Dressing")
    assert service["default_price_paise"] is None and service["position"] == 2
    [doctor] = service["doctor_prices"]
    assert doctor == {
        "doctor_id": str(world.a.doctor.id),
        "own_price_paise": None,
        "price_paise": None,
    }

    # R3: names are unique among active services; prices are bounded.
    taken = _send(owner, "POST", f"{FEES}/services", {"name": "dressing", "kind": "OTHER"})
    assert (taken.status_code, taken.get_json()["error"]["code"]) == (409, "BIL_SERVICE_NAME_TAKEN")
    too_much = _send(
        owner,
        "POST",
        f"{FEES}/services",
        {"name": "Surgery", "kind": "PROCEDURE", "default_price_paise": 10_000_001},
    )
    assert too_much.status_code == 422

    consultation = _service(added.get_json(), "Consultation")
    url = f"{FEES}/services/{consultation['id']}"
    own = _send(owner, "PUT", f"{url}/doctors/{world.a.doctor.id}", {"price_paise": 60000})
    prices = _service(own.get_json(), "Consultation")["doctor_prices"][0]
    assert (prices["own_price_paise"], prices["price_paise"]) == (60000, 60000)
    cleared = _send(owner, "PUT", f"{url}/doctors/{world.a.doctor.id}", {"price_paise": None})
    assert _service(cleared.get_json(), "Consultation")["doctor_prices"][0]["price_paise"] == 50000

    # R5: only what is sent changes; null removes the default price; a service is retired.
    changed = _send(owner, "PATCH", url, {"default_price_paise": 55000}).get_json()
    assert _service(changed, "Consultation")["name"] == "Consultation"
    assert _service(changed, "Consultation")["default_price_paise"] == 55000
    unpriced = _send(owner, "PATCH", url, {"default_price_paise": None}).get_json()
    assert _service(unpriced, "Consultation")["default_price_paise"] is None
    retired = _send(owner, "PATCH", url, {"active": False}).get_json()
    assert _service(retired, "Consultation")["active"] is False
    assert _send(owner, "PATCH", url, {}).status_code == 422

    with db.connect() as conn:
        actions = [
            r.action
            for r in conn.execute(
                text(
                    "SELECT action FROM audit_events WHERE clinic_id = :c AND action LIKE 'fees.%'"
                    " ORDER BY occurred_at"
                ),
                {"c": world.a.clinic.id},
            )
        ]
    assert actions.count("fees.service_added") == 2
    assert actions.count("fees.doctor_price_set") == 2
    assert actions.count("fees.service_changed") == 3


def test_ac3_every_role_reads_the_schedule_and_only_owners_change_it(world: World) -> None:
    owner = world.client_for(world.a.owner)
    _send(owner, "POST", f"{FEES}/services", {"name": "Consultation", "kind": "CONSULTATION"})
    for user in (world.a.desk, world.a.doctor_user):
        client = world.client_for(user)
        assert client.get(FEES).status_code == 200
        refused = _send(client, "POST", f"{FEES}/services", {"name": "X-ray", "kind": "OTHER"})
        assert refused.status_code == 403
    other = world.client_for(world.b.owner)
    assert other.get(FEES).get_json()["services"] == []  # clinic A's schedule is not B's
