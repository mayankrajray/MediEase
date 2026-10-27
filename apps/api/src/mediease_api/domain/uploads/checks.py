"""What the scanner and the identifier reader answer (M7b-P7, P8; FR-UPL-02, 03; R5-R8).

The reader's answer carries the IDs it found and how, and nothing else: text, images and any
other content read from a file never leave its adapter (R8, ADR-0023).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ScanResult:
    clean: bool
    # The scanner's signature name when infected (logged as is: it names malware, not a person).
    signature: str | None = None


class ScannerUnavailable(Exception):
    """The scanner could not be reached or did not answer (retried, then rejected; R5)."""


class ReadMethod(StrEnum):
    QR = "QR"
    TEXT = "TEXT"


@dataclass(frozen=True, slots=True)
class IdentifierRead:
    """Every distinct MediEase ID found, and by which method (for logs and the decision)."""

    ids: frozenset[UUID]
    methods: frozenset[ReadMethod] = frozenset()


class UnreadableFile(Exception):
    """The file could not be decoded within the limits (R6, R7)."""
