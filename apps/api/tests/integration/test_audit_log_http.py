"""The owner's audit log over HTTP on PostgreSQL (M6a-P8; FR-AUD-03, FR-AUD-01; decision 8A)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from tests.builders import new_id
from tests.conftest import UowFactory, World
from tests.integration.test_appointments_http import _patient
from tests.integration.test_visits_http import _send

URL = "/api/v1/audit-events"


def _event(world: World, *, clinic: Any = None, **fields: Any) -> AuditEvent:
    values: dict[str, Any] = {
        "id": new_id(),
        "action": AuditAction.CLINIC_UPDATED,
        "actor_type": ActorType.SYSTEM,
        "actor_user_id": None,
        "clinic_id": (clinic or world.a.clinic).id,
        "entity_type": "clinic",
        "entity_id": (clinic or world.a.clinic).id,
        "metadata": {"fields": "name"},
        "now": datetime.now(UTC) - timedelta(minutes=5),
    }
    values.update(fields)
    return AuditEvent.record(**values)


def _record(uow_factory: UowFactory, events: list[AuditEvent]) -> None:
    with uow_factory() as uow:
        uow.audit.record_many(events)
        uow.commit()


def test_fr_aud_03_the_owner_sees_who_did_what_in_words(world: World) -> None:
    desk = world.client_for(world.a.desk)
    patient_id = _patient(desk, "Asha Rao")
    owner = world.client_for(world.a.owner)

    page = owner.get(URL).get_json()
    assert page["timezone"] == "Asia/Kolkata"
    assert page["from"] <= page["to"]
    [created] = [i for i in page["items"] if i["action"] == "patient.created"]
    assert created["action_label"] == "Registered a patient"
    assert created["category"] == "PATIENTS"
    assert created["actor"] == {
        "type": "STAFF",
        "user_id": str(world.a.desk.id),
        "label": world.a.desk.full_name,
        "role": "FRONT_DESK",
    }
    assert (created["entity_type"], created["entity_id"]) == ("patient", patient_id)
    assert created["patient_code"] is not None
    assert "ip_hash" not in str(page) and "Asha" not in str(created)
    assert {c["value"] for c in page["categories"]} >= {"PATIENTS", "APPOINTMENTS", "SIGN_IN"}


def test_fr_aud_03_filters_by_category_and_person_and_pages_newest_first(
    world: World, uow_factory: UowFactory
) -> None:
    base = datetime.now(UTC) - timedelta(hours=2)
    _record(
        uow_factory,
        [_event(world, now=base + timedelta(seconds=i)) for i in range(55)]
        + [
            _event(
                world,
                action=AuditAction.APPOINTMENT_CANCELLED,
                actor_type=ActorType.STAFF,
                actor_user_id=world.a.desk.id,
                entity_type="appointment",
                entity_id=new_id(),
                metadata={"cancel_reason": "PATIENT_REQUEST"},
            )
        ],
    )
    owner = world.client_for(world.a.owner)

    first = owner.get(f"{URL}?category=SETTINGS").get_json()
    assert len(first["items"]) == 50 and first["next_cursor"]
    times = [i["occurred_at"] for i in first["items"]]
    assert times == sorted(times, reverse=True)
    second = owner.get(f"{URL}?category=SETTINGS&cursor={first['next_cursor']}").get_json()
    ids = {i["id"] for i in first["items"]} | {i["id"] for i in second["items"]}
    assert len(ids) == len(first["items"]) + len(second["items"]) >= 55
    assert second["next_cursor"] is None

    appointments = owner.get(f"{URL}?category=APPOINTMENTS").get_json()["items"]
    assert [i["action"] for i in appointments] == ["appointment.cancelled"]
    mine = owner.get(f"{URL}?actor_user_id={world.a.desk.id}").get_json()["items"]
    assert {i["actor"]["user_id"] for i in mine} == {str(world.a.desk.id)}
    system = [i for i in first["items"] if i["actor"]["type"] == "SYSTEM"]
    assert system[0]["actor"] == {
        "type": "SYSTEM",
        "user_id": None,
        "label": "System",
        "role": None,
    }


@pytest.mark.parametrize(
    ("query", "code"),
    [
        ("from=2026-01-01&to=2026-06-30", "AUD_RANGE_TOO_LONG"),
        ("from=2026-02-01&to=2026-01-01", "REQ_VALIDATION_FAILED"),
        ("category=EVERYTHING", "REQ_VALIDATION_FAILED"),
        ("cursor=not-a-cursor", "REQ_VALIDATION_FAILED"),
        ("from=yesterday", "REQ_VALIDATION_FAILED"),
    ],
)
def test_fr_aud_03_a_bad_range_or_filter_is_refused(world: World, query: str, code: str) -> None:
    resp = world.client_for(world.a.owner).get(f"{URL}?{query}")
    assert (resp.status_code, resp.get_json()["error"]["code"]) == (422, code)


def test_fr_aud_03_only_owners_read_the_log(world: World) -> None:
    for user in (world.a.desk, world.a.doctor_user):
        client = world.client_for(user)
        assert client.get(URL).status_code == 403
        assert client.get(f"{URL}/export").status_code == 403


def test_fr_aud_03_another_clinics_entries_never_appear(
    world: World, uow_factory: UowFactory
) -> None:
    secret = _event(world, clinic=world.b.clinic, metadata={"fields": "name"})
    _record(uow_factory, [secret])
    page = world.client_for(world.a.owner).get(URL).get_json()
    assert str(secret.id) not in {i["id"] for i in page["items"]}
    assert str(world.b.clinic.id) not in str(page)
    export = world.client_for(world.a.owner).get(f"{URL}/export").get_data(as_text=True)
    assert str(secret.id) not in export and str(world.b.clinic.id) not in export


def test_fr_aud_01_the_export_is_csv_safe_and_is_itself_audited(
    world: World, uow_factory: UowFactory, session_factory: sessionmaker[Session]
) -> None:
    _record(uow_factory, [_event(world, entity_type="=HYPERLINK", metadata={"fields": "name"})])
    owner = world.client_for(world.a.owner)

    resp = owner.get(f"{URL}/export")

    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert resp.headers["Content-Disposition"].startswith('attachment; filename="audit-')
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0] == [
        "Time",
        "Person",
        "Role",
        "Category",
        "Action",
        "Record type",
        "Record ID",
        "Patient code",
        "Details",
    ]
    [hostile] = [r for r in rows[1:] if r[5].endswith("HYPERLINK")]
    assert hostile[5] == "'=HYPERLINK"
    assert hostile[1] == "System" and hostile[4] == "Changed clinic settings"
    with session_factory() as session:
        exported = session.execute(
            text("SELECT actor_user_id, metadata FROM audit_events WHERE action = 'audit.exported'")
        ).all()
    [(actor, metadata)] = exported
    assert actor == world.a.owner.id
    assert set(metadata) == {"from", "to", "rows"}
    assert int(metadata["rows"]) == len(rows) - 1
    # The next page of the log shows the export itself.
    assert "audit.exported" in {i["action"] for i in owner.get(URL).get_json()["items"]}


def test_fr_aud_03_moving_a_patient_through_the_day_reads_as_appointment_actions(
    world: World,
) -> None:
    """The log the owner reads uses the same words for every action the API records."""
    owner = world.client_for(world.a.owner)
    patient = _patient(world.client_for(world.a.desk), "Bina Shah")
    _send(owner, "PUT", f"/api/v1/patients/{patient}/consent", {"whatsapp": True, "sms": False})
    labels = {i["action"]: i["action_label"] for i in owner.get(URL).get_json()["items"]}
    assert labels["patient.consent_changed"] == "Changed messaging consent"
