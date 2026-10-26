"""Uploaded files recognised by their first bytes (M6c-P1 certificates, M6d-P6 attachments).

The type is decided by the file's signature only, never by its name or the declared content type,
and nothing is parsed: a PDF, JPEG or PNG. Each caller sets its own size limit and turns a
``FileProblem`` into its own error (``ONB_FILE_REJECTED``, ``VIS_FILE_REJECTED``).
"""

from __future__ import annotations

from enum import StrEnum

PDF = "application/pdf"
JPEG = "image/jpeg"
PNG = "image/png"

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", PDF),
    (b"\xff\xd8\xff", JPEG),
    (b"\x89PNG\r\n\x1a\n", PNG),
)

# The extensions a download is given for each type (the first is used when one is missing).
EXTENSIONS: dict[str, tuple[str, ...]] = {
    PDF: (".pdf",),
    JPEG: (".jpg", ".jpeg"),
    PNG: (".png",),
}


class FileProblem(StrEnum):
    TYPE = "type"
    SIZE = "size"
    MISSING = "missing"


def sniff(data: bytes | None, *, max_bytes: int) -> str | FileProblem:
    """The content type the bytes are, or why they are refused (empty, too large, another type)."""
    if not data:
        return FileProblem.MISSING
    if len(data) > max_bytes:
        return FileProblem.SIZE
    for signature, content_type in _SIGNATURES:
        if data.startswith(signature):
            return content_type
    return FileProblem.TYPE
