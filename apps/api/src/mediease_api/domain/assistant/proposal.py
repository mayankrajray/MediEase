"""A write the assistant proposes and the user confirms (M7a-P3; FR-AI-01; spec assistant R7, R8).

A write tool never runs during a turn. It returns a ``Proposal``: the action, its arguments (short
strings only) and who may confirm it, until when. The adapter signs the encoded proposal
(``ports.assistant.ProposalSignerPort``); ``…/assistant/confirm`` checks the signature, that the
caller is ``subject`` (and, for staff, in ``clinic_id``), that it has not expired, and that its
``jti`` was not used, then runs the action as that caller.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.time import require_utc

PROPOSAL_TTL = timedelta(minutes=10)
MAX_ARGS = 10
MAX_ARG_LENGTH = 200


class CallerKind(StrEnum):
    PATIENT = "patient"
    STAFF = "staff"


class ProposalInvalid(DomainError):
    """R8: altered, expired, for another caller or clinic, or unknown."""

    code = "AI_PROPOSAL_INVALID"

    def __init__(self) -> None:
        super().__init__("This confirmation is no longer valid. Please ask the assistant again.")


class ProposalUsed(DomainError):
    """R8: each proposal is confirmed once."""

    code = "AI_PROPOSAL_USED"

    def __init__(self) -> None:
        super().__init__("This was already confirmed.")


@dataclass(frozen=True, slots=True)
class Proposal:
    jti: UUID
    caller: CallerKind
    subject: UUID  # the patient account, or the staff user
    clinic_id: UUID | None  # staff only
    action: str
    args: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        *,
        jti: UUID,
        caller: CallerKind,
        subject: UUID,
        clinic_id: UUID | None,
        action: str,
        args: Mapping[str, str],
        now: datetime,
    ) -> Proposal:
        now = require_utc(now, "now").replace(microsecond=0)
        if (clinic_id is None) != (caller is CallerKind.PATIENT):
            raise InvalidValue("clinic_id", "is required for staff and absent for patients")
        if len(args) > MAX_ARGS or any(len(v) > MAX_ARG_LENGTH for v in args.values()):
            raise InvalidValue("args", "too many or too long")
        return cls(
            jti=jti,
            caller=caller,
            subject=subject,
            clinic_id=clinic_id,
            action=action,
            args=MappingProxyType(dict(args)),
            issued_at=now,
            expires_at=now + PROPOSAL_TTL,
        )

    def encode(self) -> bytes:
        """Canonical JSON (sorted keys), the bytes that are signed."""
        body = {
            "v": 1,
            "jti": str(self.jti),
            "caller": self.caller.value,
            "sub": str(self.subject),
            "cid": str(self.clinic_id) if self.clinic_id else None,
            "action": self.action,
            "args": dict(self.args),
            "iat": int(self.issued_at.timestamp()),
            "exp": int(self.expires_at.timestamp()),
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def decode(cls, data: bytes) -> Proposal:
        try:
            body = json.loads(data)
            if body.get("v") != 1 or not isinstance(body.get("args"), dict):
                raise ValueError("version")
            return cls(
                jti=UUID(body["jti"]),
                caller=CallerKind(body["caller"]),
                subject=UUID(body["sub"]),
                clinic_id=UUID(body["cid"]) if body["cid"] else None,
                action=str(body["action"]),
                args=MappingProxyType({str(k): str(v) for k, v in body["args"].items()}),
                issued_at=datetime.fromtimestamp(int(body["iat"]), UTC),
                expires_at=datetime.fromtimestamp(int(body["exp"]), UTC),
            )
        except (ValueError, KeyError, TypeError):
            raise ProposalInvalid() from None

    def check(
        self, *, caller: CallerKind, subject: UUID, clinic_id: UUID | None, now: datetime
    ) -> None:
        """R8: only its own caller, in its own clinic, before it expires."""
        if (
            self.caller is not caller
            or self.subject != subject
            or self.clinic_id != clinic_id
            or require_utc(now, "now") >= self.expires_at
        ):
            raise ProposalInvalid()
