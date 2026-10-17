"""Medicine-name suggestions from the clinic's own history (M4-P3; FR-RX-10; spec R7; AC5).

Pure ranking over what the caller hands in: the doctor's favourites that match, and the medicine
names the clinic has *issued* with how many distinct visits each was prescribed in and when last.
Nothing here knows a medicine; a name the clinic never issued cannot appear (AC5).

Order: favourites first (by use, then name), then history (by distinct visits, then most recent).
Names group case- and space-insensitively; a history name already given by a favourite is not
repeated. At most ``LIMIT``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.prescriptions.library import Favourite, name_key
from mediease_api.domain.shared.errors import InvalidValue

LIMIT = 10
QUERY_MIN = 2
QUERY_MAX = 50


class SuggestionSource(StrEnum):
    FAVOURITE = "FAVOURITE"
    HISTORY = "HISTORY"


@dataclass(frozen=True, slots=True)
class HistoryName:
    """One normalised medicine name from issued prescriptions, as the repository counts it."""

    name: str  # the most recent spelling
    visits: int
    last_issued_at: datetime


@dataclass(frozen=True, slots=True)
class Suggestion:
    name: str
    source: SuggestionSource
    uses: int
    favourite_id: UUID | None = None


def clean_query(raw: str) -> str:
    """The prefix to match: trimmed, inner spaces collapsed, 2-50 characters."""
    query = " ".join(raw.split())
    if not QUERY_MIN <= len(query) <= QUERY_MAX:
        raise InvalidValue("q", f"must be {QUERY_MIN}-{QUERY_MAX} characters")
    return query


def rank(
    query: str, favourites: Sequence[Favourite], history: Sequence[HistoryName]
) -> list[Suggestion]:
    prefix = name_key(query)
    found: list[Suggestion] = []
    seen: set[str] = set()
    matching = [f for f in favourites if name_key(f.item.medicine_name).startswith(prefix)]
    for fav in sorted(matching, key=lambda f: (-f.use_count, name_key(f.name))):
        key = name_key(fav.item.medicine_name)
        if key in seen:
            continue
        seen.add(key)
        found.append(
            Suggestion(fav.item.medicine_name, SuggestionSource.FAVOURITE, fav.use_count, fav.id)
        )
    for entry in sorted(history, key=lambda h: (-h.visits, -h.last_issued_at.timestamp())):
        key = name_key(entry.name)
        if key in seen or not key.startswith(prefix):
            continue
        seen.add(key)
        found.append(Suggestion(entry.name, SuggestionSource.HISTORY, entry.visits))
    return found[:LIMIT]
