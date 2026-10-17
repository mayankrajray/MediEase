"""PDF rendering port (ADR-0012, spec prescriptions R18; M4-P4).

The application builds an ``RxDocument`` (every word already decided) and asks for its PDF. The
adapter (WeasyPrint, in-house) lays it out; it never fetches anything over the network and never
logs the document. Bytes may differ between two renders of one document, so identical downloads
come from rendering once and storing the file (R18), not from the renderer.
"""

from __future__ import annotations

from typing import Protocol

from mediease_api.domain.prescriptions.document import RxDocument


class PdfRendererPort(Protocol):
    def render(self, document: RxDocument) -> bytes:
        """The PDF. Raises on failure; nothing is kept by the renderer."""
        ...
