"""Domain errors: rule violations with a stable ``code`` (docs/ERRORS.md).

The domain raises these; the HTTP layer maps each code to a status and the
error envelope (apps/api/CLAUDE.md "Domain errors carry a stable code").
Messages and ``details`` never contain the offending value: it may be a phone
number, an email address or a name (CLAUDE.md "Never log PII").
"""

from __future__ import annotations

from typing import ClassVar


class DomainError(Exception):
    """Base class for every rule the domain enforces."""

    code: ClassVar[str]

    def __init__(self, message: str, **details: str) -> None:
        super().__init__(message)
        self.message = message
        # IDs, field names and enum values only.
        self.details: dict[str, str] = details


class InvalidValue(DomainError):
    """A value failed validation. ``field`` names it; the value is never echoed."""

    code = "REQ_VALIDATION_FAILED"

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"{field}: {reason}", field=field, reason=reason)
        self.field = field
        self.reason = reason


class InvalidTransition(DomainError):
    """A state machine refused an action in the entity's current state."""

    code = "CLN_INVALID_TRANSITION"

    def __init__(self, entity: str, state: str, action: str) -> None:
        super().__init__(
            f"Cannot {action} a {entity} that is {state}.",
            entity=entity,
            state=state,
            action=action,
        )


class NotFound(DomainError):
    """The entity does not exist — or belongs to another clinic (spec R8)."""

    code = "REQ_NOT_FOUND"

    def __init__(self, entity: str) -> None:
        super().__init__(f"{entity} not found.", entity=entity)
