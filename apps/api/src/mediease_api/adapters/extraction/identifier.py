"""Reading the MediEase ID from an uploaded file, with no OCR (M7b-P8; FR-UPL-03; ADR-0023).

``PrescriptionIdentifierReader`` implements ``IdentifierReaderPort`` (prescription-uploads R6-R8).
It looks for exactly two things, in this order, and nothing else:

1. **The QR code** (``MEDIEASE-RX:1:<uuid>``): a PDF's first pages rendered at 216 dpi, or the
   image itself, decoded with zxing-cpp for QR symbols only.
2. **The printed code in a PDF's text layer** (a layout-3 PDF as MediEase issued it): the text is
   searched for the exact code grammar (``domain/prescriptions/verification.py``).

A photographed or scanned page has no text layer, so its printed code is not read: there is no
OCR, and no model looks at the file. Without a readable QR the user types the code instead (R9).

What leaves this module is an ``IdentifierRead``: the distinct IDs found and the methods that found
them. The text, the pixels and everything else read from the file stay here and are dropped (R8):
the medicines, names and dates printed on an upload are never used, so an edited document can only
point at a prescription, never change what it says.

Limits (R6, R7), each answered ``UnreadableFile``: an image over 40 megapixels (checked from its
header, before it is decoded), a PDF of more than 50 pages, a password, a damaged file. Only the
first 2 pages are read, each rendered at no more than 40 megapixels.
"""

from __future__ import annotations

import io
import warnings
from uuid import UUID

import pypdfium2 as pdfium
import structlog
import zxingcpp
from PIL import Image

from mediease_api.domain.prescriptions.verification import codes_in_text, parse_payload
from mediease_api.domain.shared.files import JPEG, PDF, PNG
from mediease_api.domain.uploads.checks import IdentifierRead, ReadMethod, UnreadableFile

logger = structlog.get_logger(__name__)

MAX_PIXELS = 40_000_000
MAX_PDF_PAGES = 50
PAGES_READ = 2
# 216 dpi: the printed QR (17 mm at error correction M) decodes reliably at A5 and A4 (M7a-P1).
RENDER_SCALE = 3.0


def _qr_ids(image: Image.Image) -> set[UUID]:
    found: set[UUID] = set()
    for code in zxingcpp.read_barcodes(
        image, formats=zxingcpp.BarcodeFormats(zxingcpp.BarcodeFormat.QRCode)
    ):
        candidate = parse_payload(code.text)
        if candidate is not None:
            found.add(candidate)
    return found


class PrescriptionIdentifierReader:
    def __init__(self, *, max_pixels: int = MAX_PIXELS) -> None:
        self._max_pixels = max_pixels

    def read(self, data: bytes, content_type: str) -> IdentifierRead:
        if content_type == PDF:
            return self._read_pdf(data)
        if content_type in (JPEG, PNG):
            return self._read_image(data)
        raise UnreadableFile(f"unsupported type {content_type}")

    # --- Images -------------------------------------------------------------------------------

    def _read_image(self, data: bytes) -> IdentifierRead:
        try:
            with warnings.catch_warnings():
                # Pillow's own bomb guard warns, then raises; both are refusals here.
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    width, height = image.size  # from the header: nothing decoded yet
                    if width * height > self._max_pixels:
                        raise UnreadableFile("image too large")
                    image.load()
                    ids = _qr_ids(image.convert("L"))
        except UnreadableFile:
            raise
        except (
            OSError,
            ValueError,
            SyntaxError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise UnreadableFile("image could not be decoded") from exc
        return IdentifierRead(
            ids=frozenset(ids), methods=frozenset({ReadMethod.QR}) if ids else frozenset()
        )

    # --- PDFs ---------------------------------------------------------------------------------

    def _read_pdf(self, data: bytes) -> IdentifierRead:
        try:
            document = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as exc:  # damaged, or needs a password
            raise UnreadableFile("pdf could not be opened") from exc
        try:
            pages = len(document)
            if pages == 0 or pages > MAX_PDF_PAGES:
                raise UnreadableFile("pdf page count out of range")
            from_qr: set[UUID] = set()
            from_text: set[UUID] = set()
            for index in range(min(pages, PAGES_READ)):
                page = document[index]
                try:
                    textpage = page.get_textpage()
                    try:
                        from_text |= codes_in_text(textpage.get_text_range())
                    finally:
                        textpage.close()
                    width, height = page.get_size()  # points (1/72 inch)
                    pixels = width * height * RENDER_SCALE * RENDER_SCALE
                    scale = RENDER_SCALE
                    if pixels > self._max_pixels:
                        scale = RENDER_SCALE * (self._max_pixels / pixels) ** 0.5
                    bitmap = page.render(scale=scale, grayscale=True)
                    try:
                        from_qr |= _qr_ids(bitmap.to_pil())
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        except pdfium.PdfiumError as exc:
            raise UnreadableFile("pdf could not be read") from exc
        finally:
            document.close()
        methods = set()
        if from_qr:
            methods.add(ReadMethod.QR)
        if from_text:
            methods.add(ReadMethod.TEXT)
        return IdentifierRead(ids=frozenset(from_qr | from_text), methods=frozenset(methods))
