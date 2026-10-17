"""Patient links over HTTP (M4-P5; FR-RX-07, 08; spec R9-R13, R19, R20; AC2, AC3, AC10).

Real PostgreSQL. The public routes are called without a session, as the patient page's server
does, with the view token from ``verify`` in ``X-Link-View``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import Engine, create_engine, text
from werkzeug.test import TestResponse

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.domain.links import token as tokens
from tests.conftest import World, make_db_app
from tests.integration.test_appointments_http import _in_parallel
from tests.integration.test_prescriptions_http import (
    SENTINEL,
    _audit,
    _code,
    _draft,
    _fill,
    _issued,
    _two_visits,
)
from tests.integration.test_visits_http import _send

BASE = "/api/v1/public/links"


@pytest.fixture
def db(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_engine(migrated_database_url)
    yield engine
    engine.dispose()


def _link(world: World, rx_id: str, client: FlaskClient | None = None) -> dict[str, Any]:
    desk = client or world.client_for(world.a.desk)
    resp = desk.get(f"/api/v1/prescriptions/{rx_id}/link")
    assert resp.status_code == 200, resp.get_json()
    body: dict[str, Any] = resp.get_json()
    return body


def _token(link: dict[str, Any]) -> str:
    return str(link["url"]).rsplit("/p/", 1)[1]


def _last4(world: World, patient_id: str) -> str:
    owner = world.client_for(world.a.owner)
    return str(owner.get(f"/api/v1/patients/{patient_id}").get_json()["phone_e164"])[-4:]


def _wrong(right: str) -> str:
    return "0000" if right != "0000" else "1111"


def _verify(client: FlaskClient, token: str, digits: str) -> TestResponse:
    return client.post(f"{BASE}/{token}/verify", json={"phone_last4": digits})


def _opened(world: World) -> tuple[FlaskClient, dict[str, Any], dict[str, Any], str, str]:
    """An issued PRD sample, its link, and a verified view token."""
    doctor, visit, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    patient = world.anonymous()
    ok = _verify(patient, token, _last4(world, visit["patient_id"]))
    assert ok.status_code == 200, ok.get_json()
    return doctor, visit, rx, token, ok.get_json()["view_token"]


def _two_opened(world: World) -> list[tuple[str, str]]:
    """Two issued prescriptions in one running session, each with a verified view."""
    doctor, *visits = _two_visits(world)
    opened = []
    for visit in visits:
        rx = _send(doctor, "POST", f"/api/v1/visits/{visit['id']}/prescriptions").get_json()
        _fill(doctor, rx)
        issued = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
        assert issued.status_code == 200, issued.get_json()
        token = _token(_link(world, rx["id"]))
        ok = _verify(world.anonymous(), token, _last4(world, visit["patient_id"]))
        assert ok.status_code == 200, ok.get_json()
        opened.append((token, ok.get_json()["view_token"]))
    return opened


def _page(client: FlaskClient, token: str, view: str, lang: str | None = None) -> TestResponse:
    query = f"?lang={lang}" if lang else ""
    return client.get(f"{BASE}/{token}/prescription{query}", headers={"X-Link-View": view})


# --- R9, decision 1A: the link -------------------------------------------------------------------


def test_r9_issuing_version_1_creates_the_link_and_staff_see_it_without_content(
    world: World, db: Engine
) -> None:
    _, _, rx = _issued(world)
    [(_, issued)] = _audit(db, "prescription.issued")
    link = _link(world, rx["id"])
    assert link["id"] == issued["link_id"]
    assert set(link) == {"id", "url", "expires_at", "locked", "open_count", "last_opened_at"}
    assert link["url"].startswith("http://localhost:3000/p/")
    assert len(_token(link)) <= 104
    assert (link["locked"], link["open_count"]) == (False, 0)
    assert _link(world, rx["id"]) == link  # the same link every time

    public = world.anonymous().get(f"{BASE}/{_token(link)}")
    assert public.status_code == 200
    assert public.get_json() == {
        "clinic_name": world.a.clinic.name,
        "language": "en",
        "locked": False,
        "challenge_required": True,
    }
    assert public.headers["Cache-Control"] == "no-store"
    assert public.headers["X-Robots-Tag"] == "noindex, nofollow"


def test_a_draft_has_no_link(world: World) -> None:
    _, _, rx = _draft(world)
    resp = world.client_for(world.a.desk).get(f"/api/v1/prescriptions/{rx['id']}/link")
    assert (resp.status_code, _code(resp)) == (409, "RX_NOT_ISSUED")


@pytest.mark.parametrize(
    "mangle",
    [
        lambda t: t[:-2] + ("AA" if t[-2:] != "AA" else "BB"),  # the MAC
        lambda t: t.split(".")[0] + ".AAAA." + t.split(".")[2],  # the claims
        lambda t: "garbage",
        lambda t: t + ".x",
    ],
)
def test_r9_a_changed_token_is_invalid(world: World, mangle: Any) -> None:
    _, _, rx = _issued(world)
    bad = mangle(_token(_link(world, rx["id"])))
    resp = world.anonymous().get(f"{BASE}/{bad}")
    assert (resp.status_code, _code(resp)) == (404, "LINK_INVALID")


def test_nfr_08_a_token_naming_another_clinic_is_invalid(world: World) -> None:
    """Re-signing is impossible without the key, so claims cannot be moved between clinics."""
    _, _, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    parts = tokens.split(token)
    claims = tokens.read_link_claims(parts)
    moved = replace(claims, cid=world.b.clinic.id)
    forged_claims = tokens.signing_input(
        tokens.Kind.LINK, parts.key_id, tokens.link_claims_bytes(moved)
    )
    forged = tokens.assemble(forged_claims, parts.mac)
    resp = world.anonymous().get(f"{BASE}/{forged}")
    assert (resp.status_code, _code(resp)) == (404, "LINK_INVALID")


# --- R10, R13, AC3: the challenge ----------------------------------------------------------------


def test_r10_r13_the_right_digits_open_the_page_and_write_one_open(
    world: World, db: Engine
) -> None:
    _, visit, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    patient = world.anonymous()
    right = _last4(world, visit["patient_id"])

    wrong = _verify(patient, token, _wrong(right))
    assert (wrong.status_code, _code(wrong)) == (401, "LINK_CHALLENGE_FAILED")
    assert wrong.get_json()["error"]["details"] == {"attempts_left": "4"}

    no_view = patient.get(f"{BASE}/{token}/prescription")
    assert (no_view.status_code, _code(no_view)) == (401, "LINK_CHALLENGE_REQUIRED")

    ok = _verify(patient, token, right)
    assert ok.status_code == 200
    view = ok.get_json()["view_token"]
    page = _page(patient, token, view)
    assert page.status_code == 200
    [(_, opened)] = _audit(db, "patient_link.opened")
    assert opened == {"version": "1", "prescription_id": rx["id"]}
    [(_, failed)] = _audit(db, "patient_link.challenge_failed")
    assert failed == {"attempt": "1"}
    with db.connect() as conn:
        actor = conn.execute(
            text("SELECT actor_type, actor_user_id FROM audit_events WHERE action = :a"),
            {"a": "patient_link.opened"},
        ).one()
    assert tuple(actor) == ("PATIENT_LINK", None)
    assert _link(world, rx["id"])["open_count"] == 1


def test_ac3_five_wrong_attempts_lock_the_link_until_front_desk_resets_it(
    world: World, db: Engine
) -> None:
    _, visit, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    patient = world.anonymous()
    right = _last4(world, visit["patient_id"])
    codes = [_code(_verify(patient, token, _wrong(right))) for _ in range(5)]
    assert codes == ["LINK_CHALLENGE_FAILED"] * 4 + ["LINK_LOCKED"]
    sixth = _verify(patient, token, right)
    assert (sixth.status_code, _code(sixth)) == (423, "LINK_LOCKED")  # AC3
    assert world.anonymous().get(f"{BASE}/{token}").get_json()["locked"] is True
    assert len(_audit(db, "patient_link.challenge_failed")) == 5
    assert len(_audit(db, "patient_link.locked")) == 1

    desk = world.client_for(world.a.desk)
    reset = _send(desk, "POST", f"/api/v1/prescriptions/{rx['id']}/link/reset")
    assert reset.status_code == 200 and reset.get_json()["locked"] is False
    again = _send(desk, "POST", f"/api/v1/prescriptions/{rx['id']}/link/reset")
    assert (again.status_code, _code(again)) == (409, "LINK_NOT_LOCKED")
    assert _verify(patient, token, right).status_code == 200
    assert len(_audit(db, "patient_link.reset")) == 1


def test_ac3_concurrent_wrong_answers_never_pass_five(world: World) -> None:
    _, visit, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    wrong = _wrong(_last4(world, visit["patient_id"]))
    results = _in_parallel([lambda: _verify(world.anonymous(), token, wrong)] * 8)
    codes = sorted(_code(r) for r in results)
    assert codes.count("LINK_CHALLENGE_FAILED") == 4
    assert codes.count("LINK_LOCKED") == 4


def test_the_challenge_takes_exactly_four_digits(world: World) -> None:
    _, _, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    for bad in ("123", "12345", "abcd", ""):
        resp = _verify(world.anonymous(), token, bad)
        assert (resp.status_code, _code(resp)) == (422, "REQ_VALIDATION_FAILED")


# --- The view token (decision 3A) ----------------------------------------------------------------


def test_decision_3a_a_view_works_only_for_its_link_and_only_for_30_minutes(
    world: World, migrated_database_url: str
) -> None:
    (token, view), (other_token, other_view) = _two_opened(world)
    patient = world.anonymous()
    assert _page(patient, token, view).status_code == 200
    swapped = _page(patient, token, other_view)
    assert (swapped.status_code, _code(swapped)) == (401, "LINK_CHALLENGE_REQUIRED")
    forged = _page(patient, token, view[:-2] + ("AA" if view[-2:] != "AA" else "BB"))
    assert (forged.status_code, _code(forged)) == (401, "LINK_CHALLENGE_REQUIRED")
    as_link = _page(patient, token, token)  # a link token is never a view
    assert (as_link.status_code, _code(as_link)) == (401, "LINK_CHALLENGE_REQUIRED")

    class Later(SystemClock):
        def now(self):  # type: ignore[no-untyped-def]
            return super().now() + timedelta(minutes=31)

    later = make_db_app(migrated_database_url, clock=Later()).test_client()
    expired = _page(later, token, view)
    assert (expired.status_code, _code(expired)) == (401, "LINK_CHALLENGE_REQUIRED")
    assert _page(later, other_token, other_view).status_code == 401


# --- R11, R12, R19, R20, AC2, AC10: the page -----------------------------------------------------


def test_ac2_the_page_has_the_sample_with_the_dilution_under_how_to_give(world: World) -> None:
    _, _, rx, token, view = _opened(world)
    page = _page(world.anonymous(), token, view).get_json()
    [medicine] = page["medicines"]
    fields = {f["label"]: f["value"] for f in medicine["fields"]}
    assert medicine["name"] == "Syrup X"
    assert (
        fields["How to give"] == "Shake well before use; Mix in 10 ml boiled cooled water of water"
    )
    assert fields["When to take"] == "Twice a day, morning and night, after food"
    assert page["clinic_name"] == world.a.clinic.name
    assert page["doctor_name"] == rx["doctor_snapshot"]["display_name"]
    assert page["updated_note"] is None
    assert page["advice"][0]["heading"] == "Diet"


def test_r19_ac10_the_switch_shows_hindi_labels_and_the_doctors_text_as_written(
    world: World,
) -> None:
    _, _, _, token, view = _opened(world)
    page = _page(world.anonymous(), token, view, "hi").get_json()
    assert page["language"] == "hi" and page["medicines_heading"] == "दवाइयाँ"
    fields = {f["label"]: f["value"] for f in page["medicines"][0]["fields"]}
    assert fields["कब लें"] == "दिन में दो बार, सुबह और रात, खाने के बाद"
    assert page["medicines"][0]["name"] == "Syrup X"
    assert page["advice"][0]["entries"] == ["plenty of fluids"]  # English, as written
    bad = _page(world.anonymous(), token, view, "fr")
    assert (bad.status_code, _code(bad)) == (422, "REQ_VALIDATION_FAILED")


def test_r11_after_a_revision_the_same_link_shows_the_latest_with_the_banner(
    world: World,
) -> None:
    doctor, _, rx, token, view = _opened(world)
    v2 = _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/revise").get_json()
    item = {"medicine_name": "Syrup Z", "dose": "2 ml"}
    _send(doctor, "PUT", f"/api/v1/prescriptions/{v2['id']}", {"revision": 1, "items": [item]})
    issued = _send(doctor, "POST", f"/api/v1/prescriptions/{v2['id']}/issue", {"revision": 2})
    assert issued.status_code == 200, issued.get_json()
    page = _page(world.anonymous(), token, view).get_json()
    assert (page["version"], page["medicines"][0]["name"]) == (2, "Syrup Z")
    assert page["updated_note"].startswith("Updated by your doctor on ")
    assert _link(world, v2["id"])["url"].endswith(token)  # the chain's one link


# --- Decision 6A: replace ------------------------------------------------------------------------


def test_decision_6a_replacing_revokes_the_old_link(world: World, db: Engine) -> None:
    _, _, rx, token, _ = _opened(world)
    desk = world.client_for(world.a.desk)
    new = _send(desk, "POST", f"/api/v1/prescriptions/{rx['id']}/link/replace").get_json()
    assert _token(new) != token
    old = world.anonymous().get(f"{BASE}/{token}")
    assert (old.status_code, _code(old)) == (410, "LINK_REVOKED")
    assert world.anonymous().get(f"{BASE}/{_token(new)}").status_code == 200
    [(_, meta)] = _audit(db, "patient_link.replaced")
    assert meta["replaced_id"] and meta["prescription_id"] == rx["id"]


def test_an_expired_link_says_so(world: World, migrated_database_url: str) -> None:
    _, _, rx = _issued(world)
    token = _token(_link(world, rx["id"]))

    class Later(SystemClock):
        def now(self):  # type: ignore[no-untyped-def]
            return super().now() + timedelta(days=91)

    later = make_db_app(migrated_database_url, clock=Later()).test_client()
    resp = later.get(f"{BASE}/{token}")
    assert (resp.status_code, _code(resp)) == (410, "LINK_EXPIRED")


def test_chains_issued_before_p5_get_their_link_when_staff_ask(world: World, db: Engine) -> None:
    _, _, rx = _issued(world)
    with db.begin() as conn:
        conn.execute(text("DELETE FROM patient_links"))
    created = _link(world, rx["id"])
    assert created["open_count"] == 0
    assert len(_audit(db, "patient_link.created")) == 1
    assert _link(world, rx["id"]) == created


# --- Rate limits (decision 4A) -------------------------------------------------------------------


def test_decision_4a_more_than_20_requests_a_minute_for_one_link_are_refused(
    world: World,
) -> None:
    _, _, rx = _issued(world)
    token = _token(_link(world, rx["id"]))
    patient = world.anonymous()
    statuses = [patient.get(f"{BASE}/{token}").status_code for _ in range(21)]
    if statuses.count(429) == 0:  # the minute turned over during the loop; one more window
        statuses = [patient.get(f"{BASE}/{token}").status_code for _ in range(21)]
    assert 429 in statuses
    refused = patient.get(f"{BASE}/{token}")
    if refused.status_code == 429:
        assert _code(refused) == "LINK_RATE_LIMITED"
        assert 1 <= int(refused.headers["Retry-After"]) <= 60


# --- R12, R17: nothing clinical leaks ------------------------------------------------------------


def test_r12_r17_no_prescription_text_in_logs_audit_or_errors(
    world: World, db: Engine, json_logs: Any
) -> None:
    doctor, visit, rx = _draft(world)
    _fill(doctor, rx, items=[{"medicine_name": SENTINEL, "warnings": SENTINEL}])
    _send(doctor, "POST", f"/api/v1/prescriptions/{rx['id']}/issue", {"revision": 2})
    token = _token(_link(world, rx["id"]))
    patient = world.anonymous()
    right = _last4(world, visit["patient_id"])
    failed = _verify(patient, token, _wrong(right))
    view = _verify(patient, token, right).get_json()["view_token"]
    page = _page(patient, token, view)
    assert SENTINEL in page.get_data(as_text=True)
    logged = "".join(str(e) for e in json_logs())
    assert SENTINEL not in logged and token not in logged
    assert SENTINEL not in failed.get_data(as_text=True)
    with db.connect() as conn:
        dumped = conn.execute(text("SELECT metadata::text FROM audit_events")).scalars().all()
    assert all(SENTINEL not in m for m in dumped)
