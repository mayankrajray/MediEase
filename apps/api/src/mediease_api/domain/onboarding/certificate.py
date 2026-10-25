"""A doctor's registration certificate as uploaded (M6c-P1; spec clinic-onboarding R7).

The type is decided by the file's first bytes only, never by its name or the declared content
type, and nothing is parsed: a PDF, JPEG or PNG signature, 1 byte to 5 MB. The stored object is
private (``applications/{id}/doctor-{n}``) and read only by reviewers (P2).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.shared.errors import DomainError

MAX_CERTIFICATE_BYTES = 5 * 1024 * 1024

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


class FileProblem(StrEnum):
    TYPE = "type"
    SIZE = "size"
    MISSING = "missing"


class FileRejected(DomainError):
    """R7: a certificate that is missing, too large or not a PDF, JPEG or PNG."""

    code = "ONB_FILE_REJECTED"

    def __init__(self, position: int, reason: FileProblem) -> None:
        messages = {
            FileProblem.TYPE: "must be a PDF, JPEG or PNG file",
            FileProblem.SIZE: "must be at most 5 MB",
            FileProblem.MISSING: "is required",
        }
        super().__init__(
            f"The certificate of doctor {position} {messages[reason]}.",
            position=str(position),
            reason=reason.value,
        )
        self.position = position
        self.reason = reason


def sniff(data: bytes | None, position: int) -> str:
    """The content type the bytes are, or ``FileRejected`` naming the doctor's position."""
    if not data:
        raise FileRejected(position, FileProblem.MISSING)
    if len(data) > MAX_CERTIFICATE_BYTES:
        raise FileRejected(position, FileProblem.SIZE)
    for signature, content_type in _SIGNATURES:
        if data.startswith(signature):
            return content_type
    raise FileRejected(position, FileProblem.TYPE)


@dataclass(frozen=True, slots=True)
class Certificate:
    key: str
    content_type: str
    size: int
    sha256: str

    @classmethod
    def of(cls, application_id: UUID, position: int, data: bytes) -> Certificate:
        return cls(
            key=certificate_key(application_id, position),
            content_type=sniff(data, position),
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )


def certificate_key(application_id: UUID, position: int) -> str:
    return f"applications/{application_id}/doctor-{position}"
