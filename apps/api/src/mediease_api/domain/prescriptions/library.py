"""A doctor's favourites and templates (M4-P3; FR-RX-05; decisions 1A, 3A).

Working tools, not clinical records about a patient: each belongs to one doctor, is edited freely
with a ``revision`` (``RX_STALE``) and deleted for real. Their bodies are validated by the same
rules as a draft (``PrescriptionItem.create``, ``Advice.create``), so the builder can copy them
into a draft unchanged. Use is counted when a prescription built from them is issued.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mediease_api.domain.prescriptions.errors import Stale
from mediease_api.domain.prescriptions.prescription import (
    MAX_ITEMS,
    Advice,
    PrescriptionItem,
)
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.text import required_text
from mediease_api.domain.shared.time import require_utc

NAME_MAX = 100
MAX_FAVOURITES = 200
MAX_TEMPLATES = 50
FOLLOW_UP_DAYS_MAX = 365


class NameTaken(DomainError):
    """Names are unique per doctor, ignoring case."""

    code = "RX_NAME_TAKEN"

    def __init__(self) -> None:
        super().__init__("You already have one with that name.")


class LibraryFull(DomainError):
    """At most 200 favourites and 50 templates per doctor."""

    code = "RX_LIBRARY_FULL"

    def __init__(self, limit: int) -> None:
        super().__init__("You have reached the limit; delete one first.", limit=str(limit))


def library_name(value: str) -> str:
    """Trimmed with inner spaces collapsed, so the database's ``lower(name)`` index and
    ``name_key`` agree on what counts as the same name."""
    return required_text(" ".join(value.split()), "name", max_length=NAME_MAX)


def name_key(name: str) -> str:
    """How names compare for uniqueness: case- and space-insensitive."""
    return " ".join(name.lower().split())


@dataclass(slots=True)
class Favourite:
    """One medicine line with the doctor's usual instructions."""

    id: UUID
    clinic_id: UUID
    doctor_id: UUID
    name: str
    item: PrescriptionItem
    revision: int
    use_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        doctor_id: UUID,
        name: str,
        item: PrescriptionItem,
        now: datetime,
    ) -> Favourite:
        now = require_utc(now, "now")
        return cls(id, clinic_id, doctor_id, library_name(name), item, 1, 0, None, now, now)

    def replace(
        self, *, name: str, item: PrescriptionItem, seen_revision: int, now: datetime
    ) -> None:
        if seen_revision != self.revision:
            raise Stale(self.revision)
        self.name = library_name(name)
        self.item = item
        self.revision += 1
        self.updated_at = require_utc(now, "now")

    def record_use(self, at: datetime) -> None:
        self.use_count += 1
        self.last_used_at = require_utc(at, "at")


@dataclass(slots=True)
class Template:
    """A whole prescription body: lines, advice and an optional follow-up interval."""

    id: UUID
    clinic_id: UUID
    doctor_id: UUID
    name: str
    items: tuple[PrescriptionItem, ...]
    advice: Advice
    follow_up_days: int | None
    revision: int
    use_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def _check(items: Sequence[PrescriptionItem], advice: Advice, days: int | None) -> None:
        if len(items) > MAX_ITEMS:
            raise InvalidValue("items", f"must have at most {MAX_ITEMS}")
        if not items and advice.is_empty:
            raise InvalidValue("items", "a template needs a medicine or advice")
        if days is not None and not 1 <= days <= FOLLOW_UP_DAYS_MAX:
            raise InvalidValue("follow_up_days", f"must be 1-{FOLLOW_UP_DAYS_MAX}")

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        doctor_id: UUID,
        name: str,
        items: Sequence[PrescriptionItem],
        advice: Advice,
        follow_up_days: int | None,
        now: datetime,
    ) -> Template:
        now = require_utc(now, "now")
        cls._check(items, advice, follow_up_days)
        return cls(
            id,
            clinic_id,
            doctor_id,
            library_name(name),
            tuple(items),
            advice,
            follow_up_days,
            1,
            0,
            None,
            now,
            now,
        )

    def replace(
        self,
        *,
        name: str,
        items: Sequence[PrescriptionItem],
        advice: Advice,
        follow_up_days: int | None,
        seen_revision: int,
        now: datetime,
    ) -> None:
        if seen_revision != self.revision:
            raise Stale(self.revision)
        self._check(items, advice, follow_up_days)
        self.name = library_name(name)
        self.items = tuple(items)
        self.advice = advice
        self.follow_up_days = follow_up_days
        self.revision += 1
        self.updated_at = require_utc(now, "now")

    def record_use(self, at: datetime) -> None:
        self.use_count += 1
        self.last_used_at = require_utc(at, "at")
