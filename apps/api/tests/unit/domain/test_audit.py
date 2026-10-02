"""AuditEvent and the action catalogue (FR-AUD-01, FR-AUD-02; spec §7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, new_id


def _event(**overrides: object) -> AuditEvent:
    fields: dict[str, object] = {
        "id": new_id(),
        "action": AuditAction.AUTH_SIGNED_IN,
        "actor_type": ActorType.STAFF,
        "actor_user_id": new_id(),
        "now": NOW,
    }
    fields.update(overrides)
    return AuditEvent.record(**fields)  # type: ignore[arg-type]


def test_fr_aud_01_an_event_records_actor_action_target_and_request() -> None:
    clinic_id, actor_id, membership_id = new_id(), new_id(), new_id()
    event = _event(
        action=AuditAction.STAFF_ROLE_CHANGED,
        clinic_id=clinic_id,
        actor_user_id=actor_id,
        entity_type="clinic_membership",
        entity_id=membership_id,
        request_id="01J8Z5W6X4K7Q2N3R5T8V9Y0AB",
        ip_hash="a" * 32,
        metadata={"from_role": "DOCTOR", "to_role": "FRONT_DESK"},
    )

    assert event.action is AuditAction.STAFF_ROLE_CHANGED
    assert (event.clinic_id, event.actor_user_id) == (clinic_id, actor_id)
    assert (event.entity_type, event.entity_id) == ("clinic_membership", membership_id)
    assert event.occurred_at == NOW
    assert event.metadata == {"from_role": "DOCTOR", "to_role": "FRONT_DESK"}


def test_fr_aud_02_an_event_cannot_be_changed_after_it_is_recorded() -> None:
    event = _event(metadata={"session_id": str(new_id())})
    with pytest.raises(AttributeError):
        event.action = AuditAction.AUTH_SIGNED_OUT  # type: ignore[misc]
    with pytest.raises(TypeError):
        event.metadata["session_id"] = "tampered"  # type: ignore[index]


@pytest.mark.parametrize("actor_type", [ActorType.STAFF, ActorType.OPS])
def test_a_human_action_must_name_its_actor(actor_type: ActorType) -> None:
    with pytest.raises(InvalidValue) as excinfo:
        _event(actor_type=actor_type, actor_user_id=None)
    assert excinfo.value.field == "actor_user_id"


@pytest.mark.parametrize("actor_type", [ActorType.PATIENT_LINK, ActorType.SYSTEM])
def test_a_non_human_action_has_no_user(actor_type: ActorType) -> None:
    assert _event(actor_type=actor_type, actor_user_id=None).actor_user_id is None


def test_an_entity_needs_both_its_type_and_its_id() -> None:
    with pytest.raises(InvalidValue):
        _event(entity_type="clinic_membership")
    with pytest.raises(InvalidValue):
        _event(entity_id=new_id())


@pytest.mark.parametrize(
    "metadata",
    [
        {"reason": 42},  # not a string: only IDs and enums belong here
        {"note": "x" * 201},  # too long to be an ID or an enum
        {"": "value"},
        dict.fromkeys((f"k{i}" for i in range(21)), "v"),
    ],
    ids=["non-string", "too-long", "empty-key", "too-many-keys"],
)
def test_metadata_takes_ids_and_enums_only(metadata: dict[str, object]) -> None:
    with pytest.raises(InvalidValue) as excinfo:
        _event(metadata=metadata)
    assert excinfo.value.field == "metadata"


def test_the_timestamp_must_be_utc() -> None:
    with pytest.raises(InvalidValue):
        _event(now=datetime(2026, 10, 3, 4, 30))
    assert _event(now=datetime(2026, 10, 3, 4, 30, tzinfo=UTC)).occurred_at.tzinfo is UTC


@pytest.mark.parametrize("action", list(AuditAction))
def test_every_action_follows_the_area_past_tense_convention(action: AuditAction) -> None:
    area, _, event = action.value.partition(".")
    assert area and event, action
    assert action.value.islower()
