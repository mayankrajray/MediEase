"""AuditEvent — who did what, to which record, when (FR-AUD-01, FR-AUD-02).

An audit event is a statement about the past, so it is immutable here (frozen)
and append-only in the database: nothing in the system can edit or delete one
(AC6). It is written in the same transaction as the change it describes, so a
committed change always has its record (spec R11).

What it must never contain: names, phone numbers, email addresses, clinical
content or free text. ``metadata`` is a small map of short strings — IDs and
enum values — and the constructor enforces that shape, because an audit table
is read during disputes and breaches, which is exactly when extra personal
data would hurt most. The caller's IP arrives already hashed
(``ports.security.IpHasher``); the raw address is never stored.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.time import require_utc

MAX_METADATA_KEYS = 20
MAX_METADATA_VALUE_LENGTH = 200
MAX_ENTITY_TYPE_LENGTH = 50
MAX_REQUEST_ID_LENGTH = 64
MAX_IP_HASH_LENGTH = 64


class ActorType(StrEnum):
    """Who acted. Matches the ``actor_type`` CHECK in ``audit_events``."""

    STAFF = "STAFF"
    OPS = "OPS"
    # Used from M4: a patient opening a prescription link.
    PATIENT_LINK = "PATIENT_LINK"
    # Used from M5: a job or scheduled task with no human actor.
    SYSTEM = "SYSTEM"

    @property
    def is_human(self) -> bool:
        return self in (ActorType.STAFF, ActorType.OPS)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One recorded action. Build with ``AuditEvent.record``; the constructor rehydrates."""

    id: UUID
    action: AuditAction
    actor_type: ActorType
    occurred_at: datetime
    clinic_id: UUID | None = None
    actor_user_id: UUID | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None
    request_id: str | None = None
    # Salted HMAC of the caller's IP, never the address itself.
    ip_hash: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def record(
        cls,
        *,
        id: UUID,
        action: AuditAction,
        actor_type: ActorType,
        now: datetime,
        clinic_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        request_id: str | None = None,
        ip_hash: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> AuditEvent:
        if actor_type.is_human and actor_user_id is None:
            raise InvalidValue("actor_user_id", "is required for a staff or ops actor")
        if (entity_type is None) != (entity_id is None):
            raise InvalidValue("entity_type", "entity_type and entity_id must be given together")
        return cls(
            id=id,
            action=action,
            actor_type=actor_type,
            occurred_at=require_utc(now, "now"),
            clinic_id=clinic_id,
            actor_user_id=actor_user_id,
            entity_type=_bounded(entity_type, "entity_type", MAX_ENTITY_TYPE_LENGTH),
            entity_id=entity_id,
            request_id=_bounded(request_id, "request_id", MAX_REQUEST_ID_LENGTH),
            ip_hash=_bounded(ip_hash, "ip_hash", MAX_IP_HASH_LENGTH),
            metadata=_clean_metadata(metadata or {}),
        )


def _bounded(value: str | None, field_name: str, max_length: int) -> str | None:
    if value is None:
        return None
    if not value or len(value) > max_length:
        raise InvalidValue(field_name, f"must be 1-{max_length} characters")
    return value


def _clean_metadata(metadata: Mapping[str, str]) -> Mapping[str, str]:
    """IDs and enums only: short string values, a handful of keys, read-only."""
    if len(metadata) > MAX_METADATA_KEYS:
        raise InvalidValue("metadata", f"must have at most {MAX_METADATA_KEYS} keys")
    for key, value in metadata.items():
        if not key:
            raise InvalidValue("metadata", "keys must not be empty")
        if not isinstance(value, str):
            raise InvalidValue("metadata", f"value of '{key}' must be a string (IDs and enums)")
        if len(value) > MAX_METADATA_VALUE_LENGTH:
            raise InvalidValue(
                "metadata", f"value of '{key}' must be at most {MAX_METADATA_VALUE_LENGTH} chars"
            )
    return MappingProxyType(dict(metadata))
