"""Blob storage port (ADR-0012; M4-P4): generated files such as prescription PDFs.

Objects are **write-once**: ``put`` stores a key that does not exist yet, atomically (a reader
sees all of it or nothing), and leaves an existing key untouched. Keys are relative paths built
by the domain (``rx/{clinic_id}/{prescription_id}/v{version}.pdf``); every adapter refuses a key
that could escape its root. Objects are served only through the authenticated, audited API,
never by a public or pre-signed URL (docs/SECURITY_AND_COMPLIANCE.md).
"""

from __future__ import annotations

from typing import Protocol


class BlobStoragePort(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str) -> bool:
        """Store ``data`` under a new ``key``; ``False`` if the key already existed (kept)."""
        ...

    def get(self, key: str) -> bytes | None:
        """The object, or ``None`` if there is none."""
        ...

    def exists(self, key: str) -> bool: ...
