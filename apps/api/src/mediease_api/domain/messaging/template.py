"""Message templates and their variable schema (spec R8, FR-MSG-04; ARCHITECTURE §8).

Templates are data (``adapters/messaging/templates.yaml``), loaded and checked at start-up. Every
variable has a *kind*, and the kinds are the whole list of what a message may carry: clinic name,
doctor display name, a formatted date, time or token, the clinic phone and a signed link (R8).
Nothing clinical has a kind, and a value is checked against its kind before any send.

Values that are a credential (the signed link) are stored as ``[link]``: the message row records
that a link was sent, not the link itself (decision 5A).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from mediease_api.domain.messaging.errors import TemplateParamsInvalid
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import InvalidValue

_KEY = re.compile(r"[a-z][a-z0-9_]{2,63}")
_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
_E164 = re.compile(r"\+[1-9]\d{7,14}")
# WhatsApp rejects parameters with new lines, tabs or more than four spaces in a row.
_BAD_WHITESPACE = re.compile(r"[\n\r\t]| {5,}")
LINK_PLACEHOLDER = "[link]"


class TemplateCategory(StrEnum):
    # A Meta-approved utility template (business-initiated).
    UTILITY = "utility"
    # A free-form reply inside the customer-service window the patient opened (opt-out reply).
    SERVICE = "service"


class VariableKind(StrEnum):
    CLINIC_NAME = "clinic_name"
    DOCTOR_NAME = "doctor_name"
    # A date, a time, or a date with a time or token number, already formatted for the patient.
    WHEN = "when"
    PHONE = "phone"
    LINK = "link"


# The longest value of each kind (clinic and doctor names follow their own domain limits).
MAX_LENGTH: Mapping[VariableKind, int] = MappingProxyType(
    {
        VariableKind.CLINIC_NAME: 200,
        VariableKind.DOCTOR_NAME: 200,
        VariableKind.WHEN: 60,
        VariableKind.PHONE: 16,
        VariableKind.LINK: 500,
    }
)


@dataclass(frozen=True, slots=True)
class Variable:
    name: str
    kind: VariableKind


@dataclass(frozen=True, slots=True)
class LocalisedBody:
    provider_name: str
    body: str


@dataclass(frozen=True, slots=True)
class MessageTemplate:
    """One template in every language it exists in. Build with ``MessageTemplate.create``."""

    key: str
    version: int
    category: TemplateCategory
    variables: tuple[Variable, ...]
    languages: Mapping[Language, LocalisedBody]

    @classmethod
    def create(
        cls,
        *,
        key: str,
        version: int,
        category: TemplateCategory,
        variables: tuple[Variable, ...],
        languages: Mapping[Language, LocalisedBody],
    ) -> MessageTemplate:
        if not _KEY.fullmatch(key):
            raise InvalidValue("key", "must be 3-64 lowercase letters, digits or underscores")
        if version < 1:
            raise InvalidValue(f"{key}.version", "must be at least 1")
        names = [v.name for v in variables]
        if len(set(names)) != len(names):
            raise InvalidValue(f"{key}.variables", "names a variable twice")
        if set(languages) != set(Language):
            raise InvalidValue(f"{key}.languages", "must have exactly en and hi")
        for language, body in languages.items():
            if not body.provider_name.strip():
                raise InvalidValue(f"{key}.{language.value}.provider_name", "must not be empty")
            # Placeholders in order of first use must be exactly the declared variables in order:
            # providers bind parameters by position.
            used = list(dict.fromkeys(_PLACEHOLDER.findall(body.body)))
            if used != names:
                raise InvalidValue(
                    f"{key}.{language.value}.body", "must use each variable once, in order"
                )
        return cls(
            key=key,
            version=version,
            category=category,
            variables=variables,
            languages=MappingProxyType(dict(languages)),
        )

    def body(self, language: Language) -> LocalisedBody:
        return self.languages[language]

    def check(self, values: Mapping[str, str]) -> dict[str, str]:
        """R8: exactly the declared variables, each a non-empty value of its kind."""
        expected = {v.name for v in self.variables}
        if set(values) != expected:
            raise TemplateParamsInvalid(self.key, "variables do not match the template")
        checked: dict[str, str] = {}
        for variable in self.variables:
            value = values[variable.name]
            if not isinstance(value, str) or not value.strip():
                raise TemplateParamsInvalid(self.key, f"{variable.name} must be non-empty text")
            if len(value) > MAX_LENGTH[variable.kind] or _BAD_WHITESPACE.search(value):
                raise TemplateParamsInvalid(self.key, f"{variable.name} is too long or malformed")
            if variable.kind is VariableKind.PHONE and not _E164.fullmatch(value):
                raise TemplateParamsInvalid(self.key, f"{variable.name} must be E.164")
            if variable.kind is VariableKind.LINK and not value.startswith(("https://", "http://")):
                raise TemplateParamsInvalid(self.key, f"{variable.name} must be an absolute URL")
            checked[variable.name] = value
        return checked

    def stored(self, values: Mapping[str, str]) -> dict[str, str]:
        """What the message row keeps: links replaced by ``[link]`` (decision 5A)."""
        return {
            v.name: LINK_PLACEHOLDER if v.kind is VariableKind.LINK else values[v.name]
            for v in self.variables
        }

    def render(self, language: Language, values: Mapping[str, str]) -> str:
        """The body with values filled in (the console adapter and tests)."""
        return _PLACEHOLDER.sub(lambda m: values[m.group(1)], self.body(language).body)
