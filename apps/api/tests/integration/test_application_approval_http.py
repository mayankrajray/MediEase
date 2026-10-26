# ruff: noqa: F811 (the `db` and `setup` fixtures are imported and used as parameters)
"""Approving an application and verifying ops-created clinics over HTTP (M6c-P3).

FR-ONB-04, 06, 08; spec clinic-onboarding R41-R49. Real PostgreSQL.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

from mediease_api.domain.jobs.job import STAFF_INVITE_KIND
from tests.conftest import World
from tests.integration.test_application_review_http import (
    OPS,
    _check,
    _csrf,
    _doctors,
    setup,  # noqa: F401
)
from tests.integration.test_clinic_applications_http import _scalar, db  # noqa: F401


def _take_and_verify_all(setup: dict[str, Any]) -> None:
    reviewer, application_id = setup["reviewer"], setup["id"]
    reviewer.post(f"{OPS}/{application_id}/take", headers=_csrf(reviewer))
    for doctor in _doctors(reviewer, application_id):
        assert _check(reviewer, application_id, doctor["id"], "VERIFIED").status_code == 200


def test_r41_approval_needs_every_doctor_verified(setup: dict[str, Any]) -> None:
    reviewer, application_id = setup["reviewer"], setup["id"]
    reviewer.post(f"{OPS}/{application_id}/take", headers=_csrf(reviewer))
    first, second = _doctors(reviewer, application_id)
    _check(reviewer, application_id, first["id"], "VERIFIED")
    _check(reviewer, application_id, second["id"], "NOT_VERIFIED")
    resp = reviewer.post(
        f"{OPS}/{application_id}/approve", json={"slug": "approved-clinic"}, headers=_csrf(reviewer)
    )
    assert resp.status_code == 422, resp.get_json()


def test_ac11_approval_creates_a_verified_clinic_and_emails_the_owner_invitation(
    setup: dict[str, Any], db: Engine
) -> None:
    reviewer, application_id = setup["reviewer"], setup["id"]
    _take_and_verify_all(setup)
    resp = reviewer.post(
        f"{OPS}/{application_id}/approve",
        json={"slug": "approved-clinic", "city": "Pune"},
        headers=_csrf(reviewer),
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    clinic = body["clinic"]
    assert body["application"]["status"] == "APPROVED"
    assert body["application"]["clinic_id"] == clinic["id"]
    assert body["invitation_delivery"] == "email"
    assert (clinic["status"], clinic["city"]) == ("ONBOARDING", "Pune")
    assert clinic["verification_source"] == "APPLICATION" and clinic["listed"] is False

    verified = _scalar(
        db,
        "SELECT count(*) FROM doctors WHERE clinic_id = :c AND verification_source = 'APPLICATION'",
        c=clinic["id"],
    )
    assert verified == 2
    invites = _scalar(
        db,
        "SELECT count(*) FROM jobs WHERE kind = :k AND clinic_id = :c",
        k=STAFF_INVITE_KIND,
        c=clinic["id"],
    )
    assert invites == 1
    # D1: the clinic is not public until the owner accepts the invitation.
    assert (
        setup["app"].test_client().get("/api/v1/public/clinics/approved-clinic").status_code == 404
    )

    again = reviewer.post(
        f"{OPS}/{application_id}/approve", json={"slug": "approved-again"}, headers=_csrf(reviewer)
    )
    assert again.status_code == 409
    assert reviewer.get(f"{OPS}?queue=decided").get_json()["items"][0]["status"] == "APPROVED"


def test_r42_a_taken_slug_leaves_nothing_behind(
    setup: dict[str, Any], world: World, db: Engine
) -> None:
    reviewer, application_id = setup["reviewer"], setup["id"]
    _take_and_verify_all(setup)
    before = _scalar(db, "SELECT count(*) FROM clinics")
    resp = reviewer.post(
        f"{OPS}/{application_id}/approve",
        json={"slug": world.a.clinic.slug},
        headers=_csrf(reviewer),
    )
    assert resp.status_code == 409, resp.get_json()
    assert _scalar(db, "SELECT count(*) FROM clinics") == before
    assert (
        _scalar(db, "SELECT count(*) FROM doctors WHERE verification_source = 'APPLICATION'") == 0
    )
    assert reviewer.get(f"{OPS}/{application_id}").get_json()["status"] == "UNDER_REVIEW"


def test_r45_a_reviewer_verifies_an_ops_created_clinic(
    setup: dict[str, Any], world: World, db: Engine
) -> None:
    reviewer, clinic, doctor = setup["reviewer"], world.b.clinic, world.b.doctor
    with db.begin() as conn:
        conn.execute(
            text(
                "UPDATE clinics SET verified_at = NULL, verified_by = NULL,"
                " verification_source = NULL WHERE id = :c"
            ),
            {"c": clinic.id},
        )
        conn.execute(
            text(
                "UPDATE doctors SET verified_at = NULL, verified_by = NULL,"
                " verification_source = NULL WHERE id = :d"
            ),
            {"d": doctor.id},
        )
    public = world.anonymous()
    slug = clinic.slug
    assert public.get(f"/api/v1/public/clinics/{slug}").status_code == 404  # FR-ONB-06

    base = f"/api/v1/ops/clinics/{clinic.id}"
    early = reviewer.post(f"{base}/verify", headers=_csrf(reviewer))
    assert early.status_code == 422
    half = reviewer.post(
        f"{base}/doctors/{doctor.id}/verify",
        json={"register_checked": True, "certificate_matches": False},
        headers=_csrf(reviewer),
    )
    assert half.status_code == 422
    done = reviewer.post(
        f"{base}/doctors/{doctor.id}/verify",
        json={"register_checked": True, "certificate_matches": True},
        headers=_csrf(reviewer),
    )
    assert done.get_json() == {"verified": True, "changed": True}
    verified = reviewer.post(f"{base}/verify", headers=_csrf(reviewer)).get_json()
    assert verified["verification_source"] == "OPS_CHECK"
    assert public.get(f"/api/v1/public/clinics/{slug}").status_code == 200
    assert setup["admin"].post(f"{base}/verify", headers=_csrf(setup["admin"])).status_code == 403
