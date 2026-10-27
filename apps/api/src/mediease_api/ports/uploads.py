"""Ports for prescription uploads (M7b; spec prescription-uploads; ADR-0023)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from mediease_api.domain.uploads.checks import IdentifierRead, ScanResult
from mediease_api.domain.uploads.upload import PrescriptionUpload


class PrescriptionUploadRepository(Protocol):
    """Uploads are owned by a patient account (platform data, not a tenant table)."""

    def add(self, upload: PrescriptionUpload) -> None: ...
    def update(self, upload: PrescriptionUpload) -> None: ...

    def get(self, upload_id: UUID, *, for_update: bool = False) -> PrescriptionUpload | None:
        """For the worker, which processes any upload by its ID."""
        ...

    def get_for_account(
        self, upload_id: UUID, account_id: UUID, *, for_update: bool = False
    ) -> PrescriptionUpload | None:
        """The account's own upload; another account's is ``None`` (answered as not found)."""
        ...

    def count_in_flight(self, account_id: UUID) -> int:
        """R2: the account's uploads still in quarantine, being scanned or read."""
        ...

    def unfinished_before(self, before: datetime, *, limit: int) -> Sequence[PrescriptionUpload]:
        """R18: uploads not yet verified or rejected that were created (or last moved) before
        ``before``, locked for update, skipping rows another transaction holds."""
        ...

    def delete_created_before(self, before: datetime) -> Sequence[str]:
        """R18: delete rows created before ``before``; returns the file keys they still held."""
        ...


class PrescriptionLookup(Protocol):
    """The upload check's reviewed cross-clinic read (prescription-uploads R11; ADR-0003): which
    clinic issued a prescription ID. IDs only; only the last-4 check uses it, and its answer is
    never shown to the uploader."""

    def clinic_of(self, prescription_id: UUID) -> UUID | None: ...


class MalwareScannerPort(Protocol):
    """R5: scans bytes before anything parses them. Raises ``ScannerUnavailable``."""

    def scan(self, data: bytes) -> ScanResult: ...


class IdentifierReaderPort(Protocol):
    """R6-R8: the MediEase IDs in a clean file. Raises ``UnreadableFile``."""

    def read(self, data: bytes, content_type: str) -> IdentifierRead: ...
