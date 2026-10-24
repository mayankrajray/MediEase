"""The medicine planner: real responses against contracts/openapi.yaml (M6b-P3)."""

from __future__ import annotations

from datetime import timedelta

from openapi_core import OpenAPI

from tests.conftest import World
from tests.contract.test_portal_linking_contract import _expect, _psend
from tests.contract.test_scheduling_contract import _send, openapi  # noqa: F401
from tests.integration.test_medicine_plan_http import AS_NEEDED, TABLET, _issue
from tests.integration.test_prescriptions_http import _draft, _today
from tests.portal_helpers import PORTAL, link_by_invite, portal_client


def test_adr_0008_the_editor_vocabulary_and_new_fields_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    doctor, _, rx = _draft(world)
    _expect(openapi, _send(doctor, "GET", "/api/v1/rx-vocabulary"), 200)
    body = {
        "revision": rx["revision"],
        "items": [TABLET, AS_NEEDED, {"medicine_name": "Tab Night", "frequency": "0-0-1-0"}],
        "starts_on": (_today() + timedelta(days=1)).isoformat(),
    }
    saved = _expect(openapi, _send(doctor, "PUT", f"/api/v1/prescriptions/{rx['id']}", body), 200)
    bad = {
        **body,
        "revision": saved["revision"],
        "items": [{"medicine_name": "X", "frequency": "0-0-0"}],
    }
    _expect(openapi, _send(doctor, "PUT", f"/api/v1/prescriptions/{rx['id']}", bad), 422)


def test_adr_0008_the_medicine_plan_matches_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    doctor, visit, rx = _draft(world)
    issued = _issue(doctor, rx, [TABLET, AS_NEEDED])
    patient = portal_client(world, "contract.plan@example.test")
    link_by_invite(world.client_for(world.a.owner), patient, visit["patient_id"])
    revised = _expect(
        openapi, _send(doctor, "POST", f"/api/v1/prescriptions/{issued['id']}/revise"), 201
    )
    _expect(openapi, _send(doctor, "GET", f"/api/v1/prescriptions/{revised['id']}"), 200)

    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/medicine-plan"), 200)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/medicine-plan?date={_today()}"), 200)
    far = (_today() + timedelta(days=40)).isoformat()
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/medicine-plan?date={far}"), 422)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/medicine-plan/courses"), 200)
    _expect(openapi, _psend(patient, "GET", f"{PORTAL}/prescriptions/{issued['id']}"), 200)

    url = f"{PORTAL}/medicine-plan/reminders"
    choice = {
        "prescription_id": issued["id"],
        "item_id": issued["items"][0]["id"],
        "slot": "MORNING",
        "enabled": True,
        "remind_at": "07:30",
    }
    _expect(openapi, _psend(patient, "PUT", url, choice), 200)
    _expect(openapi, _psend(patient, "PUT", url, {**choice, "slot": "NIGHT"}), 422)
    _expect(
        openapi, _psend(patient, "PUT", url, {**choice, "prescription_id": rx["visit_id"]}), 404
    )

    times = {"morning": "07:00", "afternoon": "13:00", "evening": "18:30", "night": "22:00"}
    _expect(openapi, _psend(patient, "PATCH", f"{PORTAL}/me", {"slot_times": times}), 200)
    _expect(
        openapi,
        _psend(patient, "PATCH", f"{PORTAL}/me", {"slot_times": {**times, "night": "06:00"}}),
        422,
    )


def test_adr_0008_dose_marks_and_history_match_the_contract(
    openapi: OpenAPI,  # noqa: F811
    world: World,
) -> None:
    """M6b-P3b: mark, change, clear, the refused windows and the history."""
    from tests.integration.test_dose_tracking_http import TABLET as DOSE_TABLET
    from tests.integration.test_dose_tracking_http import _choice

    doctor, visit, rx = _draft(world)
    issued = _issue(
        doctor, rx, [DOSE_TABLET, AS_NEEDED], starts_on=(_today() - timedelta(days=3)).isoformat()
    )
    patient = portal_client(world, "contract.doses@example.test")
    link_by_invite(world.client_for(world.a.owner), patient, visit["patient_id"])
    doses = f"{PORTAL}/medicine-plan/doses"
    last_night = _choice(issued, 1)
    _expect(openapi, _psend(patient, "PUT", doses, {**last_night, "state": "TAKEN"}), 200)
    _expect(openapi, _psend(patient, "PUT", doses, {**last_night, "state": "SKIPPED"}), 200)
    _expect(
        openapi, _psend(patient, "GET", f"{PORTAL}/medicine-plan?date={last_night['on_date']}"), 200
    )
    history = f"{PORTAL}/medicine-plan/history?prescription_id={issued['id']}"
    _expect(openapi, _psend(patient, "GET", history), 200)
    query = "&".join(f"{k}={v}" for k, v in last_night.items())
    _expect(openapi, _psend(patient, "DELETE", f"{doses}?{query}"), 200)
    _expect(openapi, _psend(patient, "PUT", doses, {**_choice(issued, 3), "state": "TAKEN"}), 409)
    _expect(
        openapi,
        _psend(patient, "PUT", doses, {**_choice(issued, 1, "AFTERNOON"), "state": "TAKEN"}),
        422,
    )
    _expect(
        openapi,
        _psend(patient, "GET", f"{PORTAL}/medicine-plan/history?prescription_id={rx['visit_id']}"),
        404,
    )
