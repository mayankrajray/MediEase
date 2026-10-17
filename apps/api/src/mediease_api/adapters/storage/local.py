"""Blob storage on a local directory (dev, CI, single-host pilots; ADR-0012).

Write-once and atomic: the bytes go to a temporary file in the target directory, are flushed to
disk (``fsync``), then hard-linked to the final name. ``link`` fails if the name exists, so an
existing object is never replaced, and a reader sees the whole file or none of it. The temporary
file is always removed. In compose the directory is the named volume ``blobs``.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from mediease_api.adapters.storage import check_key


class LocalBlobStorage:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self._root / check_key(key)).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("invalid blob key")
        return path

    def put(self, key: str, data: bytes, *, content_type: str) -> bool:
        path = self._path(key)
        if path.exists():
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.link(tmp, path)
            except FileExistsError:
                return False
            _fsync_dir(path.parent)
            return True
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)

    def get(self, key: str) -> bytes | None:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
