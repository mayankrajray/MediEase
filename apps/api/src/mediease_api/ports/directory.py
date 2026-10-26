"""The directory search read (M6c-P6; FR-DIS-01, 02, 04; ADR-0021).

A reviewed **cross-clinic** read: it selects candidate clinics and doctors from every clinic by
the public listing columns and the searcher's words, and returns IDs with a relevance score and a
place rank only. The application applies the one discoverability rule to each candidate and
reads the clinic through its own repositories, so nothing private crosses clinics here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DirectoryFilter:
    """Normalised by the caller: ``q`` lower-case and trimmed (may be empty), ``city`` lower-case,
    ``pincode`` six digits; ``None`` means not filtered."""

    q: str = ""
    city: str | None = None
    pincode: str | None = None
    specialty: str | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    clinic_id: UUID
    doctor_id: UUID | None
    score: float  # 0-1 relevance to ``q`` (0 when no words were given)
    place: int  # 0 same PIN, 1 same city, 2 same PIN district (first 3 digits), 3 elsewhere


class DirectoryReader(Protocol):
    def clinics(self, f: DirectoryFilter, *, limit: int) -> Sequence[Candidate]:
        """Listed, ``ACTIVE``, verified clinics matching the filter, best first."""
        ...

    def doctors(self, f: DirectoryFilter, *, limit: int) -> Sequence[Candidate]:
        """Active, verified, shown doctors of such clinics matching the filter, best first."""
        ...
