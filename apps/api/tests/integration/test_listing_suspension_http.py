"""The directory listing and suspension over HTTP (M6c-P4; FR-ONB-05, 09, 10; spec R50-R58).

Real PostgreSQL. Booking requests come from the clinic's own availability
(``tests/booking_helpers.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text

from tests.booking_helpers import ensure_schedule, request_in
from tests.conftest import Tenant, World
from tests.portal_helpers import PORTAL, staff_csrf

LISTING = "/api/v1/clinic/listing"
OPS = "/api/v1/ops/clinics"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _put(client: FlaskClient, url: str, body: dict[str, Any]) -> Any:
    return client.put(url, json=body, headers=staff_csrf(client))


def _post(client: FlaskClient, url: str, body: dict[str, Any] | None = None) -> Any:
    return client.post(url, json=body or {}, headers=staff_csrf(client))


def _verify_doctor(world: World, tenant: Tenant) -> None:
    ops = world.client_for(world.ops)
    resp = _post(
        ops,
        f"{OPS}/{tenant.clinic.id}/doctors/{tenant.doctor.id}/verify",
        {"register_checked": True, "certificate_matches": True},
    )
    assert resp.status_code == 200, resp.get_json()


def _with_address(world: World, tenant: Tenant) -> None:
    owner = world.client_for(tenant.owner)
    resp = owner.patch(
        "/api/v1/clinic",
        json={"address_line": "1 Sample Road", "city": "Sample City", "pincode": "560001"},
        headers=staff_csrf(owner),
    )
    assert resp.status_code == 200, resp.get_json()


def test_r51_r52_listing_needs_every_requirement_and_reports_what_is_missing(
    world: World, db: Engine
) -> None:
    owner = world.client_for(world.a.owner)
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinics SET address_line = NULL WHERE id = :c"), {"c": world.a.clinic.id}
        )
    state = owner.get(LISTING).get_json()
    assert state["listed"] is False and state["discoverable"] is False
    assert state["problems"] == ["ADDRESS_MISSING", "NO_BOOKABLE_DOCTOR"]
    [doctor] = state["doctors"]
    assert doctor["problems"] == ["NOT_VERIFIED", "NO_SCHEDULE", "HIDDEN"]
    assert doctor["can_be_visible"] is False

    blocked = _put(owner, LISTING, {"listed": True})
    assert blocked.status_code == 409
    assert blocked.get_json()["error"]["code"] == "CLN_LISTING_BLOCKED"
    assert (
        blocked.get_json()["error"]["details"]["problems"] == "ADDRESS_MISSING,NO_BOOKABLE_DOCTOR"
    )

    # R53: only an active verified doctor can be shown.
    hidden = _put(owner, f"{LISTING}/doctors/{world.a.doctor.id}", {"visible": True})
    assert hidden.get_json()["error"]["code"] == "CLN_DOCTOR_NOT_VERIFIED"

    _verify_doctor(world, world.a)
    ensure_schedule(world, world.a)
    _with_address(world, world.a)
    shown = _put(owner, f"{LISTING}/doctors/{world.a.doctor.id}", {"visible": True}).get_json()
    assert shown["problems"] == [] and shown["doctors"][0]["problems"] == []
    listed = _put(owner, LISTING, {"listed": True}).get_json()
    assert listed["listed"] is True and listed["discoverable"] is True
    assert listed["listed_at"] is not None

    # The front desk may read the listing, never change it.
    desk = world.client_for(world.a.desk)
    assert desk.get(LISTING).status_code == 200
    assert _put(desk, LISTING, {"listed": False}).status_code == 403
    unlisted = _put(owner, LISTING, {"listed": False}).get_json()
    assert unlisted["listed"] is False and unlisted["listed_at"] is None

    with db.connect() as conn:
        actions = [
            r.action
            for r in conn.execute(
                text("SELECT action FROM audit_events WHERE clinic_id = :c ORDER BY occurred_at"),
                {"c": world.a.clinic.id},
            )
        ]
    assert actions.count("clinic.listing_changed") == 2
    assert "doctor.visibility_changed" in actions


def test_r46_a_registration_change_hides_nothing_but_ends_discoverability(
    world: World,
) -> None:
    owner = world.client_for(world.a.owner)
    _verify_doctor(world, world.a)
    ensure_schedule(world, world.a)
    _with_address(world, world.a)
    _put(owner, f"{LISTING}/doctors/{world.a.doctor.id}", {"visible": True})
    assert _put(owner, LISTING, {"listed": True}).get_json()["discoverable"] is True
    changed = owner.patch(
        f"/api/v1/clinic/doctors/{world.a.doctor.id}",
        json={"registration_number": "NEW-12345"},
        headers=staff_csrf(owner),
    )
    assert changed.status_code == 200 and changed.get_json()["verified_at"] is None
    state = owner.get(LISTING).get_json()
    assert state["listed"] is True and state["discoverable"] is False
    assert state["problems"] == ["NO_BOOKABLE_DOCTOR"]


def test_ac15_suspension_withdraws_open_requests_and_tells_the_patients(
    world: World, db: Engine
) -> None:
    patient, request_id = request_in(world, world.a, "suspended.requester@example.test")
    admin = world.client_for(world.ops)
    other = _post(admin, f"{OPS}/{world.a.clinic.id}/suspend", {"reason": "OTHER"})
    assert other.status_code == 422  # R56: OTHER needs a note

    resp = _post(admin, f"{OPS}/{world.a.clinic.id}/suspend", {"reason": "VERIFICATION_PROBLEM"})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["clinic"]["status"] == "SUSPENDED" and body["requests_withdrawn"] == 1
    row = (
        db.connect()
        .execute(
            text(
                "SELECT status, decline_reason, decided_by_type FROM booking_requests WHERE id = :i"
            ),
            {"i": request_id},
        )
        .one()
    )
    assert tuple(row) == ("DECLINED", "CLINIC_UNAVAILABLE", "SYSTEM")

    # R57: the patient reads it in the portal, although the clinic is suspended.
    notices = patient.get(f"{PORTAL}/notifications").get_json()["items"]
    assert [n["kind"] for n in notices] == ["booking.declined"]
    # R56: the public page is gone at once; staff are refused.
    anon = world.anonymous()
    assert anon.get(f"/api/v1/public/clinics/{world.a.clinic.slug}").status_code == 404
    staff = world.client_for(world.a.desk).get("/api/v1/clinic")
    assert staff.get_json()["error"]["code"] == "CLN_SUSPENDED"
    again = _post(admin, f"{OPS}/{world.a.clinic.id}/suspend", {"reason": "PAYMENT"})
    assert again.status_code == 409

    reactivated = _post(admin, f"{OPS}/{world.a.clinic.id}/reactivate")
    assert reactivated.status_code == 200 and reactivated.get_json()["status"] == "ACTIVE"
    assert anon.get(f"/api/v1/public/clinics/{world.a.clinic.slug}").status_code == 200
    assert _post(admin, f"{OPS}/{world.a.clinic.id}/reactivate").status_code == 422

    with db.connect() as conn:
        audit = conn.execute(
            text(
                "SELECT action, metadata FROM audit_events WHERE clinic_id = :c"
                " AND action IN ('clinic.suspended', 'clinic.reactivated') ORDER BY occurred_at"
            ),
            {"c": world.a.clinic.id},
        ).all()
    assert [a.action for a in audit] == ["clinic.suspended", "clinic.reactivated"]
    assert audit[0].metadata == {"reason": "VERIFICATION_PROBLEM", "requests_withdrawn": "1"}


def test_r58_only_ops_admins_suspend(world: World) -> None:
    owner = world.client_for(world.a.owner)
    assert (
        _post(owner, f"{OPS}/{world.a.clinic.id}/suspend", {"reason": "PAYMENT"}).status_code == 403
    )


def test_another_clinics_doctor_is_not_found(world: World) -> None:
    owner = world.client_for(world.a.owner)
    resp = _put(owner, f"{LISTING}/doctors/{world.b.doctor.id}", {"visible": False})
    assert resp.status_code == 404
