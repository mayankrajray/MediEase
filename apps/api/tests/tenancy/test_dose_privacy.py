"""Dose records are the patient's alone (M6b-P3b; patient portal R50-R52, AC21; D4).

A permanent suite, like the portal scope's:

- another account cannot mark, clear or read a dose of a record it is not linked to;
- no staff or ops route reaches dose records: only the patient's own use cases touch
  ``tenant.dose_records``, and only the support command touches the cross-clinic
  ``dose_lifecycle`` (a source check, so a new reader fails here and has to be reviewed);
- staff reading the same patient's data see nothing of the marks.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from tests.conftest import World
from tests.integration.test_dose_tracking_http import DOSES, SENTINEL, TABLET, _choice, _mark
from tests.integration.test_medicine_plan_http import AS_NEEDED, _issue
from tests.integration.test_portal_http import portal_csrf
from tests.integration.test_prescriptions_http import _draft, _today
from tests.portal_helpers import PORTAL, link_by_invite, portal_client

SRC = Path(__file__).resolve().parents[2] / "src" / "mediease_api"

# Who may touch dose records. Anything else is a new reader to review against R50.
DOSE_READERS = {"application/portal/doses.py", "application/portal/medicines.py"}
LIFECYCLE_USERS = {"delivery/cli/dose_data.py"}


def _users_of(pattern: str) -> set[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("adapters/") or rel.startswith("ports/"):
            continue  # the definitions themselves
        if re.search(pattern, path.read_text(encoding="utf-8")):
            found.add(rel)
    return found


def test_r50_only_the_patients_own_use_cases_read_dose_records() -> None:
    # A call on the repository (``counts.dose_records`` in the purge is a number, not a read).
    assert _users_of(r"\.dose_records\.\w+\(") == DOSE_READERS
    assert _users_of(r"\.dose_lifecycle\.\w+\(") == LIFECYCLE_USERS


def test_ac21_another_account_cannot_mark_clear_or_read_a_dose(world: World) -> None:
    doctor, visit, rx = _draft(world)
    issued = _issue(
        doctor, rx, [TABLET, AS_NEEDED], starts_on=(_today() - timedelta(days=3)).isoformat()
    )
    owner = world.client_for(world.a.owner)
    bina = portal_client(world, "bina.doses@example.test", name="Bina Shah")
    link_by_invite(owner, bina, visit["patient_id"])
    asha = portal_client(world, "asha.doses@example.test", name="Asha Rao")
    choice = _choice(issued, 1)

    for resp in (
        _mark(asha, choice, "TAKEN"),
        asha.delete(DOSES, query_string=choice, headers=portal_csrf(asha)),
        asha.get(f"{PORTAL}/medicine-plan/history", query_string={"prescription_id": issued["id"]}),
    ):
        assert (resp.status_code, resp.get_json()["error"]["code"]) == (404, "REQ_NOT_FOUND")
    assert _mark(bina, choice, "TAKEN").status_code == 200


def test_r50_staff_reading_the_patient_see_nothing_of_the_marks(world: World) -> None:
    doctor, visit, rx = _draft(world)
    issued = _issue(
        doctor, rx, [TABLET, AS_NEEDED], starts_on=(_today() - timedelta(days=3)).isoformat()
    )
    owner = world.client_for(world.a.owner)
    patient = portal_client(world, "private.doses@example.test")
    link_by_invite(owner, patient, visit["patient_id"])
    assert _mark(patient, _choice(issued, 1), "SKIPPED").status_code == 200

    patient_id = visit["patient_id"]
    for staff in (owner, doctor, world.client_for(world.a.desk)):
        for url in (
            f"/api/v1/patients/{patient_id}",
            f"/api/v1/patients/{patient_id}/visits",
            f"/api/v1/patients/{patient_id}/portal",
            f"/api/v1/prescriptions/{issued['id']}",
        ):
            body = staff.get(url).get_data(as_text=True)
            assert "SKIPPED" not in body and "marked_at" not in body, url
    ops = world.client_for(world.ops)
    clinic = ops.get(f"/api/v1/ops/clinics/{world.a.clinic.id}").get_data(as_text=True)
    assert "SKIPPED" not in clinic and SENTINEL not in clinic
