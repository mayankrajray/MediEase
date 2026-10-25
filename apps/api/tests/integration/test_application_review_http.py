# ruff: noqa: F811 (the `db` fixture is imported and used as a parameter)
"""Reviewing clinic applications over HTTP (M6c-P2; FR-ONB-03, 05; spec R24-R40).

Real PostgreSQL; certificates in a memory store; the emails rendered by running the job handler.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, text

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.application.onboarding.jobs import PurgeApplications
from mediease_api.domain.identity.user import OpsRole
from tests.builders import a_user
from tests.conftest import CHEAP_HASHER, DEMO_PASSWORD, UowFactory, World, make_db_app
from tests.integration.test_clinic_applications_http import (
    OWNER_EMAIL,
    PDF,
    MemoryStore,
    _confirm_token,
    _jobs,
    _run_email,
    _scalar,
    db,  # noqa: F401
    solo_body,
    submit,
)

OPS = "/api/v1/ops/applications"


def _csrf(client: FlaskClient) -> dict[str, str]:
    cookie = client.get_cookie("me_csrf", path="/")
    return {"X-CSRF-Token": cookie.value} if cookie is not None else {}


def _sign_in(app: Any, email: str) -> FlaskClient:
    client: FlaskClient = app.test_client()
    resp = client.post(
        "/api/v1/auth/sign-in", json={"identifier": email, "password": DEMO_PASSWORD}
    )
    assert resp.status_code == 200, resp.get_json()
    return client


@pytest.fixture
def setup(
    migrated_database_url: str,
    uow_factory: UowFactory,
    world: World,
    db: Engine,
) -> dict[str, Any]:
    store = MemoryStore()
    app = make_db_app(migrated_database_url, blob_storage=store)
    anon = app.test_client()
    body = solo_body(kind="CLINIC")
    body["doctors"].append(
        {
            "name": "Dr. Second Synthetic",
            "qualification": "MBBS",
            "council": "Delhi Medical Council",
            "registration_number": "DMC-22",
        }
    )
    reference = submit(anon, body, {1: PDF, 2: PDF}).get_json()["reference"]
    anon.post(
        "/api/v1/public/applications/confirm", json={"token": _confirm_token(db, uow_factory)}
    )
    application_id = _scalar(db, "SELECT id FROM clinic_applications")
    roles: dict[str, Any] = {}
    with uow_factory() as uow:
        for name, granted in (
            ("reviewer", frozenset({OpsRole.REVIEWER})),
            ("admin", frozenset({OpsRole.ADMIN})),
        ):
            user = a_user(
                full_name=f"Ops {name}",
                is_platform_ops=True,
                ops_roles=granted,
                password_hash=CHEAP_HASHER.hash(DEMO_PASSWORD),
            )
            uow.users.add(user)
            roles[name] = user
        uow.commit()
    return {
        "app": app,
        "store": store,
        "reference": reference,
        "id": str(application_id),
        "reviewer": _sign_in(app, roles["reviewer"].email.value),
        "admin": _sign_in(app, roles["admin"].email.value),
        "both": _sign_in(app, world.ops.email.value),  # type: ignore[union-attr]
    }


def _doctors(client: FlaskClient, application_id: str) -> list[dict[str, Any]]:
    return list(client.get(f"{OPS}/{application_id}").get_json()["doctors"])


def _check(client: FlaskClient, application_id: str, doctor_id: str, result: str) -> Any:
    both = result == "VERIFIED"
    return client.put(
        f"{OPS}/{application_id}/doctors/{doctor_id}/check",
        json={"register_checked": True, "certificate_matches": both, "result": result},
        headers=_csrf(client),
    )


def test_r24_only_reviewers_review_and_only_admins_run_the_console(
    setup: dict[str, Any], world: World
) -> None:
    reviewer, admin, both = setup["reviewer"], setup["admin"], setup["both"]
    assert reviewer.get(OPS).status_code == 200
    assert admin.get(OPS).status_code == 403
    assert reviewer.get("/api/v1/ops/clinics").status_code == 403
    assert admin.get("/api/v1/ops/clinics").status_code == 200
    assert both.get(OPS).status_code == 200  # an ops user from before M6c holds both roles
    assert world.client_for(world.a.owner).get(OPS).status_code == 403


def test_ac10_a_reviewer_takes_checks_and_rejects_with_the_reason_emailed(
    setup: dict[str, Any],
    db: Engine,
    uow_factory: UowFactory,
) -> None:
    reviewer, application_id = setup["reviewer"], setup["id"]
    [item] = reviewer.get(f"{OPS}?queue=waiting").get_json()["items"]
    assert (item["reference"], item["status"]) == (setup["reference"], "PENDING")

    detail = reviewer.get(f"{OPS}/{application_id}").get_json()
    assert detail["owner_email"] == OWNER_EMAIL and len(detail["doctors"]) == 2
    first, second = detail["doctors"]
    cert = reviewer.get(f"{OPS}/{application_id}/doctors/{first['id']}/certificate")
    assert cert.status_code == 200 and cert.data == PDF
    assert cert.headers["X-Content-Type-Options"] == "nosniff"
    assert cert.mimetype == "application/pdf"

    # Checks need the application under review (R29).
    early = _check(reviewer, application_id, first["id"], "VERIFIED")
    assert early.get_json()["error"]["code"] == "ONB_NOT_UNDER_REVIEW"
    taken = reviewer.post(f"{OPS}/{application_id}/take", headers=_csrf(reviewer))
    assert taken.get_json()["status"] == "UNDER_REVIEW"
    again = setup["both"].post(f"{OPS}/{application_id}/take", headers=_csrf(setup["both"]))
    assert (again.status_code, again.get_json()["error"]["code"]) == (409, "ONB_ALREADY_TAKEN")

    checked = _check(reviewer, application_id, first["id"], "VERIFIED").get_json()
    assert checked["doctors"][0]["check"]["result"] == "VERIFIED" and not checked["all_verified"]
    refused = reviewer.put(
        f"{OPS}/{application_id}/doctors/{second['id']}/check",
        json={"register_checked": False, "certificate_matches": True, "result": "VERIFIED"},
        headers=_csrf(reviewer),
    )
    assert refused.status_code == 422
    assert _check(reviewer, application_id, second["id"], "NOT_VERIFIED").status_code == 200

    no_message = reviewer.post(
        f"{OPS}/{application_id}/reject", json={"reason": "OTHER"}, headers=_csrf(reviewer)
    )
    assert no_message.status_code == 422
    rejected = reviewer.post(
        f"{OPS}/{application_id}/reject",
        json={"reason": "REGISTRATION_NOT_FOUND", "message": "Doctor 2 is not on the register."},
        headers=_csrf(reviewer),
    ).get_json()
    assert (rejected["status"], rejected["decision_reason"]) == (
        "REJECTED",
        "REGISTRATION_NOT_FOUND",
    )
    assert reviewer.get(f"{OPS}?queue=decided").get_json()["items"][0]["status"] == "REJECTED"

    [email] = _run_email(db, uow_factory, _jobs(db)[-1])
    assert email.to.value == OWNER_EMAIL
    assert "medical council's register" in email.text
    assert "Doctor 2 is not on the register." in email.text and "/apply" in email.text

    with db.connect() as conn:
        actions = [
            r.action
            for r in conn.execute(
                text(
                    "SELECT action FROM audit_events WHERE actor_type = 'OPS' ORDER BY occurred_at"
                )
            )
        ]
        metadata = json.dumps(
            [r.metadata for r in conn.execute(text("SELECT metadata FROM audit_events"))]
        )
    assert actions.count("application.viewed") >= 1
    for action in (
        "application.certificate_viewed",
        "application.taken",
        "application.doctor_checked",
        "application.rejected",
    ):
        assert action in actions
    assert "not on the register" not in metadata


def test_r35_rejected_applications_are_purged_after_180_days(
    setup: dict[str, Any],
    db: Engine,
    uow_factory: UowFactory,
) -> None:
    reviewer, application_id = setup["reviewer"], setup["id"]
    reviewer.post(f"{OPS}/{application_id}/take", headers=_csrf(reviewer))
    reviewer.post(
        f"{OPS}/{application_id}/reject", json={"reason": "DUPLICATE"}, headers=_csrf(reviewer)
    )
    with db.begin() as conn:
        conn.execute(
            text("UPDATE clinic_applications SET decided_at = decided_at - interval '181 days'")
        )
    removed = PurgeApplications(
        uow=uow_factory(), clock=SystemClock(), storage=setup["store"]
    ).execute()
    assert removed == 1 and setup["store"].objects == {}
    assert _scalar(db, "SELECT count(*) FROM clinic_applications") == 0


def test_unknown_and_unconfirmed_applications_are_not_found(setup: dict[str, Any]) -> None:
    reviewer = setup["reviewer"]
    assert reviewer.get(f"{OPS}/0192f0a0-0000-7000-8000-000000000999").status_code == 404
    assert reviewer.get(f"{OPS}?queue=bogus").status_code == 422
