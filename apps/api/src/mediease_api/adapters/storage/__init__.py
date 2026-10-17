"""Adapters for ``BlobStoragePort`` (ADR-0012): a local volume and an S3-compatible store."""

from __future__ import annotations

import re

# rx/<uuid>/<uuid>/v1.pdf and the like: relative, no "..", no empty or hidden segments.
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*")


def check_key(key: str) -> str:
    """The key, if it is a safe relative path; ``ValueError`` otherwise (never echoes it)."""
    if len(key) > 512 or not _KEY.fullmatch(key) or ".." in key:
        raise ValueError("invalid blob key")
    return key
