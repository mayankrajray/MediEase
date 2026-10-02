"""Email addresses: trimmed and lower-cased so one person has one identity.

Structural validation only (one ``@``, a dotted domain, RFC 5321 lengths). An
address is proved real by using it, not by a regular expression.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mediease_api.domain.shared.errors import InvalidValue

_MAX_LENGTH = 254
_MAX_LOCAL_LENGTH = 64
_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


@dataclass(frozen=True, slots=True, repr=False)
class EmailAddress:
    """A validated, lower-case email address."""

    value: str

    def __post_init__(self) -> None:
        if self.value != self.value.strip().lower():
            raise InvalidValue("email", "must be trimmed and lower-case")
        if len(self.value) > _MAX_LENGTH or any(c.isspace() for c in self.value):
            raise InvalidValue("email", "is not a valid email address")
        local, at, domain = self.value.rpartition("@")
        if not at or not local or "@" in local or len(local) > _MAX_LOCAL_LENGTH:
            raise InvalidValue("email", "is not a valid email address")
        labels = domain.split(".")
        if len(labels) < 2 or not all(_DOMAIN_LABEL.fullmatch(label) for label in labels):
            raise InvalidValue("email", "is not a valid email address")

    @classmethod
    def parse(cls, raw: str, field: str = "email") -> EmailAddress:
        """Normalise user input, or raise ``InvalidValue`` naming ``field``."""
        try:
            return cls(raw.strip().lower())
        except InvalidValue as exc:
            raise InvalidValue(field, exc.reason) from None

    def masked(self) -> str:
        """``a***@example.com``: enough to recognise, not enough to contact."""
        local, _, domain = self.value.rpartition("@")
        return f"{local[0]}***@{domain}"

    def __repr__(self) -> str:
        return f"EmailAddress({self.masked()!r})"

    __str__ = __repr__
