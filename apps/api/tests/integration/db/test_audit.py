"""The audit log against real PostgreSQL (FR-AUD-01, FR-AUD-02; spec R11, AC6).

Proves an event round-trips with everything an investigation needs, that the
database itself refuses to change or remove one, and that the support view
reports activity without exposing anything clinical.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.identity.membership import Role
from tests.builders import NOW, a_clinic, a_membership, a_user, new_id
from tests.conftest import UowFactory

SessionFactory = sessionmaker[Session]

# Columns a support engineer may see: IDs, enums, counts and timestamps only.
EXPECTED_VIEW_COLUMNS = {
    "clinic_id",
    "clinic_name",
    "status",
    "active_owners",
    "active_doctors",
    "active_front_desk",
    "last_sign_in_at",
    "audit_events_7d",
    "audit_events_30d",
    "last_event_at",
}


def _rows(session_factory: SessionFactory, query: str) -> list[dict[str, Any]]:
    with session_factory() as session:
        return [dict(row) for row in session.execute(text(query)).mappings()]


def _event(**overrides: object) -> AuditEvent:
    fields: dict[str, object] = {
        "id": new_id(),
        "action": AuditAction.AUTH_SIGNED_IN,
        "actor_type": ActorType.STAFF,
        "now": NOW,
    }
    fields.update(overrides)
    return AuditEvent.record(**fields)  # type: ignore[arg-type]


def test_fr_aud_01_an_event_round_trips_with_actor_target_and_request(
    uow_factory: UowFactory, session_factory: SessionFactory
) -> None:
    clinic, actor = a_clinic(), a_user()
    membership_id = new_id()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(actor)
        uow.audit.record(
            _event(
                action=AuditAction.STAFF_ROLE_CHANGED,
                actor_user_id=actor.id,
                clinic_id=clinic.id,
                entity_type="clinic_membership",
                entity_id=membership_id,
                request_id="01J8Z5W6X4K7Q2N3R5T8V9Y0AB",
                ip_hash="f" * 32,
                metadata={"from_role": "DOCTOR", "to_role": "FRONT_DESK"},
            )
        )
        uow.commit()

    rows = _rows(session_factory, "SELECT * FROM audit_events")
    assert len(rows) == 1
    row = rows[0]
    assert row["action"] == "staff.role_changed"
    assert row["actor_type"] == "STAFF"
    assert (row["actor_user_id"], row["clinic_id"]) == (actor.id, clinic.id)
    assert (row["entity_type"], row["entity_id"]) == ("clinic_membership", membership_id)
    assert row["request_id"] == "01J8Z5W6X4K7Q2N3R5T8V9Y0AB"
    assert row["metadata"] == {"from_role": "DOCTOR", "to_role": "FRONT_DESK"}
    assert row["occurred_at"].timestamp() == NOW.timestamp()


def test_a_platform_event_has_no_clinic_and_metadata_defaults_to_empty(
    uow_factory: UowFactory, session_factory: SessionFactory
) -> None:
    actor = a_user()
    with uow_factory() as uow:
        uow.users.add(actor)
        uow.audit.record(_event(actor_type=ActorType.OPS, actor_user_id=actor.id))
        uow.commit()

    row = _rows(session_factory, "SELECT * FROM audit_events")[0]
    assert row["clinic_id"] is None
    assert row["metadata"] == {}
    assert row["ip_hash"] is None


def test_r11_an_audit_row_rolls_back_with_the_change_it_describes(
    uow_factory: UowFactory, session_factory: SessionFactory
) -> None:
    """Leaving the unit of work without committing keeps neither the change nor its record."""
    user = a_user()
    with uow_factory() as uow:
        uow.users.add(user)
        uow.audit.record(_event(actor_user_id=user.id))
        # no commit

    assert _rows(session_factory, "SELECT * FROM audit_events") == []
    with uow_factory() as uow:
        assert uow.users.get(user.id) is None


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET action = 'tampered'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
    ids=["update", "delete", "truncate"],
)
def test_ac6_fr_aud_02_the_database_refuses_to_change_or_remove_an_event(
    uow_factory: UowFactory, session_factory: SessionFactory, statement: str
) -> None:
    user = a_user()
    with uow_factory() as uow:
        uow.users.add(user)
        uow.audit.record(_event(actor_user_id=user.id))
        uow.commit()

    with session_factory() as session:
        with pytest.raises(DatabaseError, match="AUD_APPEND_ONLY"):
            session.execute(text(statement))
        session.rollback()

    assert len(_rows(session_factory, "SELECT id FROM audit_events")) == 1


def test_fr_ops_04_clinic_activity_view_reports_use_without_clinical_data(
    uow_factory: UowFactory, session_factory: SessionFactory
) -> None:
    clinic = a_clinic(name="Alpha Sample Clinic")
    owner, doctor, desk = a_user(), a_user(), a_user()
    # The 7/30-day windows are relative to the database's clock, so the event
    # is recorded "now" rather than at the builders' fixed timestamp.
    recorded_at = datetime.now(UTC)
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        for user, role in ((owner, Role.OWNER), (doctor, Role.DOCTOR), (desk, Role.FRONT_DESK)):
            uow.users.add(user)
            uow.tenant(clinic.id).memberships.add(a_membership(clinic.id, user.id, role))
        stored_owner = uow.users.get(owner.id)
        assert stored_owner is not None
        stored_owner.record_successful_sign_in(now=NOW)
        uow.users.update(stored_owner)
        uow.audit.record(
            _event(
                action=AuditAction.STAFF_ROLE_CHANGED,
                actor_user_id=owner.id,
                clinic_id=clinic.id,
                entity_type="clinic_membership",
                entity_id=new_id(),
                now=recorded_at,
            )
        )
        uow.commit()

    rows = _rows(session_factory, "SELECT * FROM v_clinic_activity")
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == EXPECTED_VIEW_COLUMNS
    assert row["clinic_name"] == "Alpha Sample Clinic"
    assert (row["active_owners"], row["active_doctors"], row["active_front_desk"]) == (1, 1, 1)
    assert row["last_sign_in_at"].timestamp() == NOW.timestamp()
    assert row["last_event_at"].timestamp() == pytest.approx(recorded_at.timestamp())
    assert (row["audit_events_7d"], row["audit_events_30d"]) == (1, 1)


def test_fr_ops_04_a_clinic_with_no_activity_still_appears(
    uow_factory: UowFactory, session_factory: SessionFactory
) -> None:
    clinic = a_clinic()
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.commit()

    row = _rows(session_factory, "SELECT * FROM v_clinic_activity")[0]
    assert (row["active_owners"], row["audit_events_7d"]) == (0, 0)
    assert row["last_sign_in_at"] is None and row["last_event_at"] is None
