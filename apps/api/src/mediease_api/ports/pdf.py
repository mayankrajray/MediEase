"""PDF rendering port (ADR-0012, spec prescriptions R18; M4-P4).

The application builds an ``RxDocument`` (every word already decided) and asks for its PDF. The
adapter (WeasyPrint, in-house) lays it out; it never fetches anything over the network and never
logs the document. The same document gives the same bytes, so a stored PDF can be compared.
"""

from __future__ import annotations

from typing import Protocol

from mediease_api.domain.prescriptions.document import RxDocument


class PdfRendererPort(Protocol):
    def render(self, document: RxDocument) -> bytes:
        """The PDF. Raises on failure; nothing is kept by the renderer."""
        ...
