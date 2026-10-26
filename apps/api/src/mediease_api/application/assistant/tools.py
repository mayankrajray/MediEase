"""Tools: what the model may ask for (M7a-P3; FR-AI-01; spec assistant R6, R7; ADR-0024).

A tool is a thin wrapper over an existing use case, built for one caller and one request, so it
can never reach more than that caller could through the API. A **read** tool runs and returns a
``ToolResult``: a ``summary`` written by our code in the caller's language (what the console
adapter says, and a model may use) and ``data`` (structured, screen-level fields only). A
**write** tool never runs in a turn: ``prepare`` checks and describes it and ``perform`` runs it
when the user confirms (``confirm.py``), as the caller of that request.

Arguments come from the model, so they are untrusted: ``Args`` reads them with types and limits
and raises ``ToolArgumentError``, which goes back to the model as an error result (it can then ask
the user), never to the user as a failure.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from mediease_api.domain.assistant.explain import Explanation
from mediease_api.domain.assistant.llm import JsonValue, ToolSpec
from mediease_api.domain.patients.patient import Language

MAX_TEXT = 200


class ToolKind(StrEnum):
    READ = "READ"
    WRITE = "WRITE"


class ToolArgumentError(Exception):
    """The model's arguments were missing or malformed; told to the model, not the user."""


@dataclass(frozen=True, slots=True)
class ToolResult:
    summary: str
    data: Mapping[str, JsonValue] = field(default_factory=lambda: MappingProxyType({}))
    # Set by ``explain_prescription``: the record's own text and what a reply may use (R10).
    explanation: Explanation | None = None


@dataclass(frozen=True, slots=True)
class Prepared:
    """A write ready for confirmation: what the user is shown, and the checked arguments."""

    summary: str
    args: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Tool:
    spec: ToolSpec
    kind: ToolKind
    run: Callable[[Args], ToolResult] | None = None
    prepare: Callable[[Args], Prepared] | None = None
    # Runs a confirmed write; returns what to tell the user.
    perform: Callable[[Mapping[str, str]], str] | None = None

    @property
    def name(self) -> str:
        return self.spec.name


def spec(
    name: str,
    description: str,
    properties: Mapping[str, Mapping[str, JsonValue]] | None = None,
    required: tuple[str, ...] = (),
) -> ToolSpec:
    """A JSON Schema object for the tool's arguments."""
    props: dict[str, JsonValue] = {k: dict(v) for k, v in (properties or {}).items()}
    schema: dict[str, JsonValue] = {
        "type": "object",
        "properties": props,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return ToolSpec(name=name, description=description, parameters=schema)


def string(description: str) -> dict[str, JsonValue]:
    return {"type": "string", "description": description}


def integer(description: str) -> dict[str, JsonValue]:
    return {"type": "integer", "description": description}


def boolean(description: str) -> dict[str, JsonValue]:
    return {"type": "boolean", "description": description}


class Args:
    """The model's arguments for one call, read with types and limits."""

    def __init__(self, values: Mapping[str, JsonValue]) -> None:
        self._values = values

    def text(self, name: str, *, required: bool = True, max_length: int = MAX_TEXT) -> str | None:
        value = self._values.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                raise ToolArgumentError(f"'{name}' is required")
            return None
        if not isinstance(value, str | int | float):
            raise ToolArgumentError(f"'{name}' must be text")
        text = str(value).strip()
        if len(text) > max_length:
            raise ToolArgumentError(f"'{name}' is too long")
        return text

    def required_text(self, name: str, *, max_length: int = MAX_TEXT) -> str:
        value = self.text(name, max_length=max_length)
        assert value is not None
        return value

    def uuid(self, name: str) -> UUID:
        try:
            return UUID(self.required_text(name, max_length=36))
        except ValueError:
            raise ToolArgumentError(f"'{name}' must be an ID from a tool result") from None

    def optional_uuid(self, name: str) -> UUID | None:
        return self.uuid(name) if self._values.get(name) not in (None, "") else None

    def instant(self, name: str, *, required: bool = True) -> datetime | None:
        text = self.text(name, required=required, max_length=40)
        if text is None:
            return None
        try:
            value = datetime.fromisoformat(text)
        except ValueError:
            raise ToolArgumentError(f"'{name}' must be an ISO time from a tool result") from None
        if value.tzinfo is None:
            raise ToolArgumentError(f"'{name}' must include its time zone")
        return value

    def day(self, name: str, *, required: bool = True) -> date | None:
        text = self.text(name, required=required, max_length=10)
        if text is None:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            raise ToolArgumentError(f"'{name}' must be a date like 2026-10-28") from None

    def number(self, name: str, *, minimum: int = 1, maximum: int = 100) -> int | None:
        value = self._values.get(name)
        if value is None or value == "":
            return None
        try:
            number = int(str(value))
        except ValueError:
            raise ToolArgumentError(f"'{name}' must be a whole number") from None
        if not minimum <= number <= maximum:
            raise ToolArgumentError(f"'{name}' must be between {minimum} and {maximum}")
        return number

    def flag(self, name: str) -> bool:
        value = self._values.get(name)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ToolArgumentError(f"'{name}' must be true or false")


def first_name(full_name: str) -> str:
    return (full_name.split() or ["Patient"])[0]


def say(language: Language, english: str, hindi: str) -> str:
    """One line of tool wording in the caller's language."""
    return hindi if language is Language.HI else english
