"""Plans, the trial and limits over HTTP (M6d-P7; FR-SUB-01; spec plans-and-trial AC1-AC8).

Real PostgreSQL. Clinics are made through the ops console, so each has its subscription row; the
world's clinics are written straight to the database and have none (treated as Plus, R2).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from mediease_api.domain.identity.membership import Role
from tests.conftest import World
from tests.integration.test_onboarding_http import (
    OPS_CLINICS,
    _accept,
    _csrf,
    _invite,
    _patch,
    _post,
    _token_from,
)

SUBSCRIPTION = "/api/v1/clinic/subscription"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _code(resp: TestResponse) -> tuple[int, str]:
    return resp.status_code, str(resp.get_json()["error"]["code"])


def _clinic(ops: FlaskClient, plan: str, slug: str = "plan-sample-clinic") -> str:
    resp = _post(ops, OPS_CLINICS, {"name": "Plan Sample Clinic", "slug": slug, "plan": plan})
    assert resp.status_code == 201, resp.get_json()
    return str(resp.get_json()["id"])


def _doctor(client: FlaskClient, path: str, n: int) -> TestResponse:
    return _post(
        client,
        path,
        {
            "display_name": f"Dr. Plan {n}",
            "qualification": "MBBS",
            "registration_number": f"PLAN-{n:04d}",
            "registration_council": "Sample State Medical Council",
        },
    )


def _listed(ops: FlaskClient, clinic_id: str) -> dict[str, Any]:
    items = ops.get(OPS_CLINICS).get_json()["items"]
    return dict(next(i["subscription"] for i in items if i["id"] == clinic_id))


def _owner(world: World, ops: FlaskClient, clinic_id: str, email: str) -> FlaskClient:
    invited = _invite(ops, clinic_id, Role.OWNER, email, "Plan Owner")
    assert invited.status_code == 201, invited.get_json()
    owner = world.anonymous()
    assert _accept(owner, _token_from(invited)).status_code == 200
    return owner


def test_ac1_ac2_a_solo_clinic_takes_one_doctor_and_two_people(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _clinic(ops, "SOLO")
    assert _listed(ops, clinic) == {
        "plan": "SOLO",
        "plan_name": "Solo",
        "trial_state": "NOT_STARTED",
        "trial_ends_at": None,
        "trial_days_left": None,
    }

    doctors = f"{OPS_CLINICS}/{clinic}/doctors"
    assert _doctor(ops, doctors, 1).status_code == 201
    second = _doctor(ops, doctors, 2)
    assert _code(second) == (409, "SUB_LIMIT_REACHED")
    assert second.get_json()["error"]["details"] == {
        "plan": "SOLO",
        "limit": "doctors",
        "allowed": "1",
    }

    owner = _owner(world, ops, clinic, "plan.owner@example.test")
    assert _invite(ops, clinic, Role.FRONT_DESK, "plan.desk@example.test").status_code == 201
    third = _invite(ops, clinic, Role.FRONT_DESK, "plan.third@example.test")
    assert _code(third) == (409, "SUB_LIMIT_REACHED")
    assert third.get_json()["error"]["details"]["limit"] == "users"
    # The owner's own invite is limited the same way.
    by_owner = _post(
        owner,
        "/api/v1/clinic/staff",
        {"full_name": "Fourth", "role": "FRONT_DESK", "email": "plan.fourth@example.test"},
    )
    assert _code(by_owner) == (409, "SUB_LIMIT_REACHED")

    # R3, R6: the owner sees the plan, what is used and the trial that started on joining.
    seen = owner.get(SUBSCRIPTION).get_json()
    assert (seen["plan"], seen["trial_state"], seen["trial_days_left"]) == ("SOLO", "ACTIVE", 14)
    assert seen["limits"] == {"doctors": 1, "users": 2}
    assert seen["usage"] == {"doctors": 1, "users": 2}
    assert seen["trial_started_at"] is not None


def test_ac3_ac4_r8_ops_change_the_plan_but_never_below_what_is_used(
    world: World, db: Engine
) -> None:
    ops = world.client_for(world.ops)
    clinic = _clinic(ops, "SOLO")
    doctors = f"{OPS_CLINICS}/{clinic}/doctors"
    assert _doctor(ops, doctors, 1).status_code == 201

    plan = f"{OPS_CLINICS}/{clinic}/plan"
    changed = ops.put(plan, json={"plan": "CLINIC"}, headers=_csrf(ops))
    assert changed.status_code == 200, changed.get_json()
    assert (changed.get_json()["plan"], changed.get_json()["limits"]["doctors"]) == ("CLINIC", 3)
    assert _doctor(ops, doctors, 2).status_code == 201

    back = ops.put(plan, json={"plan": "SOLO"}, headers=_csrf(ops))
    assert _code(back) == (409, "SUB_PLAN_TOO_SMALL")
    assert back.get_json()["error"]["details"] == {
        "plan": "SOLO",
        "limit": "doctors",
        "allowed": "1",
        "used": "2",
    }
    assert _code(ops.put(plan, json={"plan": "GOLD"}, headers=_csrf(ops)))[0] == 422
    unknown = ops.put(
        f"{OPS_CLINICS}/{world.a.doctor.id}/plan", json={"plan": "PLUS"}, headers=_csrf(ops)
    )
    assert _code(unknown) == (404, "REQ_NOT_FOUND")
    owner = world.client_for(world.a.owner)
    forbidden = owner.put(plan, json={"plan": "PLUS"}, headers=_csrf(owner))
    assert forbidden.status_code == 403

    with db.connect() as conn:
        rows = conn.execute(
            text("SELECT metadata FROM audit_events WHERE action = 'subscription.plan_changed'")
        ).all()
    assert [r[0] for r in rows] == [{"from": "SOLO", "to": "CLINIC"}]


def test_ac5_r5_bringing_a_doctor_back_takes_a_place(world: World) -> None:
    ops = world.client_for(world.ops)
    clinic = _clinic(ops, "SOLO")
    first = _doctor(ops, f"{OPS_CLINICS}/{clinic}/doctors", 1).get_json()["id"]
    owner = _owner(world, ops, clinic, "plan.back@example.test")

    assert _patch(owner, f"/api/v1/clinic/doctors/{first}", {"is_active": False}).status_code == 200
    assert _doctor(owner, "/api/v1/clinic/doctors", 2).status_code == 201
    again = _patch(owner, f"/api/v1/clinic/doctors/{first}", {"is_active": True})
    assert _code(again) == (409, "SUB_LIMIT_REACHED")
    assert owner.get(SUBSCRIPTION).get_json()["usage"]["doctors"] == 1


def test_ac6_r4_accepting_rechecks_the_seat(world: World, db: Engine) -> None:
    ops = world.client_for(world.ops)
    clinic = _clinic(ops, "CLINIC")
    tokens = [
        _token_from(_invite(ops, clinic, Role.FRONT_DESK, f"plan.seat{n}@example.test"))
        for n in range(3)
    ]
    # A plan that no longer fits (written by hand: ops cannot make one smaller than its use).
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinic_subscriptions SET plan = 'SOLO' WHERE clinic_id = :c"),
            {"c": clinic},
        )
    assert _code(_accept(world.anonymous(), tokens[0])) == (409, "SUB_LIMIT_REACHED")


def test_ac7_d5_an_ended_trial_shows_but_locks_nothing(world: World, db: Engine) -> None:
    ops = world.client_for(world.ops)
    clinic = _clinic(ops, "CLINIC")
    owner = _owner(world, ops, clinic, "plan.trial@example.test")
    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE clinic_subscriptions SET trial_started_at = now() - interval '15 days',"
                " trial_ends_at = now() - interval '1 day' WHERE clinic_id = :c"
            ),
            {"c": clinic},
        )
    seen = owner.get(SUBSCRIPTION).get_json()
    assert (seen["trial_state"], seen["trial_days_left"]) == ("ENDED", 0)
    assert _listed(ops, clinic)["trial_state"] == "ENDED"
    # Nothing is locked: the owner still works.
    assert _doctor(owner, "/api/v1/clinic/doctors", 1).status_code == 201


def test_ac8_r2_r6_a_clinic_from_before_plans_and_who_may_read(world: World) -> None:
    owner = world.client_for(world.a.owner)
    seen = owner.get(SUBSCRIPTION).get_json()
    assert (seen["plan"], seen["trial_state"], seen["limits"]) == (
        "PLUS",
        "NONE",
        {"doctors": 5, "users": None},
    )
    assert seen["usage"] == {"doctors": 1, "users": 4}
    assert world.client_for(world.a.desk).get(SUBSCRIPTION).status_code == 403
    assert world.client_for(world.a.doctor_user).get(SUBSCRIPTION).status_code == 403
