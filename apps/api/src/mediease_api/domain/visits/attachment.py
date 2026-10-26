"""A report attached to a visit (M6d-P6; FR-VIS-04; spec visit-attachments, decision B8, D7).

A scanned or downloaded report (a PDF, JPEG or PNG of at most 10 MB, recognised by its first
bytes) kept privately under ``attachments/{clinic}/{visit}/{id}``. Clinical content: opening one
needs ``CLINICAL_VIEW`` and is audited. Its uploader may delete it within 24 hours; after that it
stays, like an addendum. The visit's doctor may share it with the patient's portal.

The file name is the patient's and the clinic's business: it is stored and shown, never logged.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID

from mediease_api.domain.shared import files
from mediease_api.domain.shared.errors import DomainError
from mediease_api.domain.shared.files import FileProblem

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_PER_VISIT = 20
DELETE_WINDOW = timedelta(hours=24)
FILENAME_MAX = 120

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")


class AttachmentRejected(DomainError):
    """R2: the file is missing, larger than 10 MB, or not a PDF, JPEG or PNG."""

    code = "VIS_FILE_REJECTED"

    def __init__(self, reason: FileProblem) -> None:
        messages = {
            FileProblem.TYPE: "The report must be a PDF, JPEG or PNG file.",
            FileProblem.SIZE: "The report must be at most 10 MB.",
            FileProblem.MISSING: "Choose a file to attach.",
        }
        super().__init__(messages[reason], reason=reason.value)
        self.reason = reason


class AttachmentLimitReached(DomainError):
    """R3: a visit holds at most 20 reports."""

    code = "VIS_ATTACHMENT_LIMIT"

    def __init__(self) -> None:
        super().__init__(
            f"A visit can hold at most {MAX_PER_VISIT} reports.", limit=str(MAX_PER_VISIT)
        )


class AttachmentNotYours(DomainError):
    """R8: only the person who attached a report may delete it."""

    code = "VIS_ATTACHMENT_NOT_YOURS"

    def __init__(self) -> None:
        super().__init__("Only the person who attached this report can delete it.")


class AttachmentLocked(DomainError):
    """R8: 24 hours after upload a report stays for good."""

    code = "VIS_ATTACHMENT_LOCKED"

    def __init__(self, locked_at: datetime) -> None:
        super().__init__(
            "This report was attached more than 24 hours ago and can no longer be deleted.",
            locked_at=locked_at.isoformat(),
        )


class AttachmentUploadFailed(DomainError):
    """R4: the file could not be stored; nothing was kept."""

    code = "VIS_UPLOAD_FAILED"

    def __init__(self) -> None:
        super().__init__("The report could not be stored. Try again.")


def check_file(data: bytes | None) -> str:
    """The file's content type, or ``AttachmentRejected``."""
    found = files.sniff(data, max_bytes=MAX_ATTACHMENT_BYTES)
    if isinstance(found, FileProblem):
        raise AttachmentRejected(found)
    return found


def clean_filename(raw: str | None, content_type: str) -> str:
    """R5: the name shown and offered on download.

    The last path segment only, no control characters, spaces collapsed, at most 120 characters,
    and an extension that matches the file's real type (added when it does not).
    """
    name = unicodedata.normalize("NFC", raw or "")
    name = re.split(r"[\\/]", name)[-1]
    name = _SPACES.sub(" ", _CONTROL.sub("", name)).strip().strip(".")
    extensions = files.EXTENSIONS[content_type]
    if not name.lower().endswith(extensions):
        name = f"{name or 'report'}{extensions[0]}"
    if len(name) > FILENAME_MAX:
        stem, dot, ext = name.rpartition(".")
        name = f"{stem[: FILENAME_MAX - len(ext) - 1].rstrip()}{dot}{ext}"
    return name


def attachment_key(clinic_id: UUID, visit_id: UUID, attachment_id: UUID) -> str:
    return f"attachments/{clinic_id}/{visit_id}/{attachment_id}"


@dataclass(frozen=True, slots=True)
class VisitAttachment:
    id: UUID
    clinic_id: UUID
    visit_id: UUID
    patient_id: UUID
    storage_key: str
    content_type: str
    size_bytes: int
    filename: str
    uploaded_by: UUID
    uploaded_at: datetime
    shared_at: datetime | None = None
    shared_by: UUID | None = None
    deleted_at: datetime | None = None
    deleted_by: UUID | None = None

    @classmethod
    def upload(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        visit_id: UUID,
        patient_id: UUID,
        data: bytes | None,
        filename: str | None,
        by: UUID,
        now: datetime,
    ) -> VisitAttachment:
        content_type = check_file(data)
        assert data is not None  # check_file refuses an empty file
        return cls(
            id=id,
            clinic_id=clinic_id,
            visit_id=visit_id,
            patient_id=patient_id,
            storage_key=attachment_key(clinic_id, visit_id, id),
            content_type=content_type,
            size_bytes=len(data),
            filename=clean_filename(filename, content_type),
            uploaded_by=by,
            uploaded_at=now,
        )

    @property
    def is_shared(self) -> bool:
        return self.shared_at is not None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def locked_at(self) -> datetime:
        return self.uploaded_at + DELETE_WINDOW

    def can_delete(self, user_id: UUID, now: datetime) -> bool:
        return user_id == self.uploaded_by and now < self.locked_at

    def delete(self, *, by: UUID, now: datetime) -> VisitAttachment:
        """R8: by its uploader, within 24 hours."""
        if by != self.uploaded_by:
            raise AttachmentNotYours()
        if now >= self.locked_at:
            raise AttachmentLocked(self.locked_at)
        return replace(self, deleted_at=now, deleted_by=by)

    def share(self, shared: bool, *, by: UUID, now: datetime) -> VisitAttachment:
        """R10: shown in the patient's portal, or no longer. Repeating either is a no-op."""
        if shared == self.is_shared:
            return self
        if shared:
            return replace(self, shared_at=now, shared_by=by)
        return replace(self, shared_at=None, shared_by=None)
