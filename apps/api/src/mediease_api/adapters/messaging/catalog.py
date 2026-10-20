"""The template catalogue, read from ``templates.yaml`` once at start-up (spec R8, decision 2A).

A malformed file, an unknown variable kind, a body whose placeholders do not match its variables,
or a missing template the code sends stops the worker before it claims anything, rather than
failing a send later. ``yaml.safe_load`` only: the file is data, never objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from importlib import resources
from types import MappingProxyType
from typing import Any

import yaml

from mediease_api.domain.messaging.jobs import REQUIRED_TEMPLATES
from mediease_api.domain.messaging.template import (
    LocalisedBody,
    MessageTemplate,
    TemplateCategory,
    Variable,
    VariableKind,
)
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import InvalidValue


class TemplateFileInvalid(ValueError):
    """The templates file cannot be used; the message says where, never a value."""


def _require(mapping: Any, key: str, where: str) -> Any:
    if not isinstance(mapping, dict) or key not in mapping:
        raise TemplateFileInvalid(f"{where}: '{key}' is missing")
    return mapping[key]


def _template(key: str, raw: Any) -> MessageTemplate:
    where = f"templates.{key}"
    try:
        variables = tuple(
            Variable(
                name=str(_require(v, "name", f"{where}.variables")),
                kind=VariableKind(_require(v, "kind", f"{where}.variables")),
            )
            for v in _require(raw, "variables", where)
        )
        languages = {
            Language(language): LocalisedBody(
                provider_name=str(_require(body, "provider_name", f"{where}.{language}")),
                body=str(_require(body, "body", f"{where}.{language}")),
            )
            for language, body in _require(raw, "languages", where).items()
        }
        raw_sms = raw.get("sms") if isinstance(raw, dict) else None
        if raw_sms is not None and not isinstance(raw_sms, dict):
            raise TemplateFileInvalid(f"{where}: 'sms' must be a mapping")
        sms = {Language(language): str(text) for language, text in (raw_sms or {}).items()}
        return MessageTemplate.create(
            key=key,
            version=int(_require(raw, "version", where)),
            category=TemplateCategory(_require(raw, "category", where)),
            variables=variables,
            languages=languages,
            sms=sms,
        )
    except TemplateFileInvalid:
        raise
    except (InvalidValue, ValueError, TypeError, AttributeError) as error:
        raise TemplateFileInvalid(f"{where}: {error}") from None


def parse_templates(text: str) -> Mapping[str, MessageTemplate]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        raise TemplateFileInvalid("templates file is not valid YAML") from None
    raw = _require(document, "templates", "file")
    if not isinstance(raw, dict):
        raise TemplateFileInvalid("file: 'templates' must be a mapping")
    templates = {str(key): _template(str(key), value) for key, value in raw.items()}
    missing = REQUIRED_TEMPLATES - set(templates)
    if missing:
        raise TemplateFileInvalid(f"file: missing templates {sorted(missing)}")
    return MappingProxyType(templates)


class YamlTemplateCatalog:
    def __init__(self, templates: Mapping[str, MessageTemplate]) -> None:
        self._templates = templates

    @classmethod
    def from_package(cls) -> YamlTemplateCatalog:
        text = (
            resources.files("mediease_api.adapters.messaging")
            .joinpath("templates.yaml")
            .read_text(encoding="utf-8")
        )
        return cls(parse_templates(text))

    def get(self, key: str) -> MessageTemplate:
        return self._templates[key]

    def template_keys(self) -> frozenset[str]:
        return frozenset(self._templates)
