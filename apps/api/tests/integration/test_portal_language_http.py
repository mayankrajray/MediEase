"""The portal's language and the clinic's clock over HTTP (M6b-P2; spec R19, R21, R22)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

from tests.conftest import World
from tests.integration.test_portal_http import PASSWORD, SIGN_UP, portal_csrf, sign_up
from tests.integration.test_prescriptions_http import _issued
from tests.portal_helpers import PORTAL, link_by_invite, portal_client

ME = f"{PORTAL}/me"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def test_r21_a_new_account_is_english_and_the_patient_switches_to_hindi(
    world: World, db: Engine
) -> None:
    patient = portal_client(world, "language.patient@example.test")
    assert patient.get(ME).get_json()["account"]["language"] == "en"

    changed = patient.patch(ME, json={"language": "hi"}, headers=portal_csrf(patient))
    assert changed.status_code == 200, changed.get_json()
    assert changed.get_json()["account"]["language"] == "hi"
    # Kept on the account: a second browser signing in sees Hindi too.
    other = world.anonymous()
    signed_in = other.post(
        f"{PORTAL}/auth/sign-in",
        json={"email": "language.patient@example.test", "password": PASSWORD},
    )
    assert signed_in.get_json()["account"]["language"] == "hi"
    with db.connect() as conn:
        assert conn.execute(text("SELECT language FROM patient_accounts")).scalar_one() == "hi"
        # A display preference: logged, never audited.
        audited = conn.execute(
            text("SELECT count(*) FROM audit_events WHERE action LIKE '%language%'")
        ).scalar_one()
        assert audited == 0


def test_r21_only_en_or_hi_and_nothing_else_in_the_body(world: World) -> None:
    patient = portal_client(world, "language.bad@example.test")
    for body in ({"language": "fr"}, {}, {"language": "hi", "full_name": "X"}):
        resp = patient.patch(ME, json=body, headers=portal_csrf(patient))
        assert resp.status_code == 422, body
        assert resp.get_json()["error"]["code"] == "REQ_VALIDATION_FAILED"
    no_csrf = patient.patch(ME, json={"language": "hi"})
    assert no_csrf.status_code == 403


def test_r21_sign_up_takes_the_body_language_then_the_cookie(world: World) -> None:
    by_body = world.anonymous().post(
        SIGN_UP,
        json={
            "full_name": "Asha Patient",
            "email": "body.lang@example.test",
            "password": PASSWORD,
            "language": "hi",
        },
    )
    assert by_body.get_json()["account"]["language"] == "hi"

    by_cookie = world.anonymous()
    by_cookie.set_cookie("me_pt_lang", "hi", path="/")
    assert (
        sign_up(by_cookie, email="cookie.lang@example.test").get_json()["account"]["language"]
        == "hi"
    )

    junk = world.anonymous()
    junk.set_cookie("me_pt_lang", "xx", path="/")
    assert sign_up(junk, email="junk.lang@example.test").get_json()["account"]["language"] == "en"


def test_r22_links_and_appointment_groups_carry_the_clinics_time_zone(world: World) -> None:
    _, visit, rx = _issued(world)
    owner = world.client_for(world.a.owner)
    patient = portal_client(world, "zone.patient@example.test")
    link_by_invite(owner, patient, visit["patient_id"])
    zone = owner.get("/api/v1/clinic").get_json()["timezone"]

    [link] = patient.get(f"{PORTAL}/links").get_json()["items"]
    assert link["clinic"]["timezone"] == zone
    [group] = patient.get(f"{PORTAL}/appointments").get_json()["items"]
    assert group["timezone"] == zone
    assert "phone_e164" in group

    # R19: without ?lang the page follows the account's language, not the record's.
    assert patient.get(f"{PORTAL}/prescriptions/{rx['id']}").get_json()["language"] == "en"
    patient.patch(ME, json={"language": "hi"}, headers=portal_csrf(patient))
    assert patient.get(f"{PORTAL}/prescriptions/{rx['id']}").get_json()["language"] == "hi"
    asked = patient.get(f"{PORTAL}/prescriptions/{rx['id']}?lang=en").get_json()
    assert asked["language"] == "en"
