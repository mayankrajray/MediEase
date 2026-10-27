"""The identifier reader and the clamd client (M7b-P7, P8; FR-UPL-02, 03; R5-R8).

The reader runs on real layout-3 PDFs from the real renderer. clamd is played by a local socket
server speaking the INSTREAM protocol (the live daemon is ``tests/integration/test_clamd_live.py``).
"""

from __future__ import annotations

import io
import socket
import struct
import threading
from collections.abc import Iterator
from uuid import UUID

import pytest
import segno
from PIL import Image

from mediease_api.adapters.extraction.identifier import PrescriptionIdentifierReader
from mediease_api.adapters.malware.clamd import ClamdScanner
from mediease_api.adapters.pdf.weasy import WeasyPrintRenderer
from mediease_api.domain.uploads.checks import ReadMethod, ScannerUnavailable, UnreadableFile
from tests.unit.adapters.test_pdf_renderer import doc_of
from tests.unit.domain.test_rx_document import issued

READER = PrescriptionIdentifierReader()


def png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def qr_png(payload: str) -> bytes:
    out = io.BytesIO()
    segno.make(payload, error="m").save(out, kind="png", scale=8, border=4)
    return out.getvalue()


def test_fr_upl_03_a_layout_3_pdf_is_read_by_qr_and_text_layer() -> None:
    rx = issued()
    pdf = WeasyPrintRenderer().render(doc_of(rx))
    read = READER.read(pdf, "application/pdf")
    assert read.ids == frozenset({rx.id})
    assert read.methods == frozenset({ReadMethod.QR, ReadMethod.TEXT})


def test_fr_upl_03_an_image_is_read_by_its_qr_only() -> None:
    rx_id = UUID("01a17a78-d5bb-733a-87e7-e442b8dbd341")
    read = READER.read(qr_png(f"MEDIEASE-RX:1:{rx_id}"), "image/png")
    assert (read.ids, read.methods) == (frozenset({rx_id}), frozenset({ReadMethod.QR}))


def test_r8_a_foreign_qr_is_no_identifier() -> None:
    read = READER.read(qr_png("https://example.test/not-ours"), "image/png")
    assert read.ids == frozenset()


def test_r7_an_image_over_the_pixel_cap_is_refused_before_decoding() -> None:
    small = PrescriptionIdentifierReader(max_pixels=100 * 100)
    with pytest.raises(UnreadableFile):
        small.read(png(Image.new("L", (101, 100), 255)), "image/png")


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (b"%PDF-1.7\nnot a pdf", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png"),
        (b"\xff\xd8\xff" + b"0" * 64, "image/jpeg"),
        (b"anything", "image/gif"),
    ],
)
def test_r6_damaged_or_unknown_files_are_unreadable(data: bytes, kind: str) -> None:
    with pytest.raises(UnreadableFile):
        READER.read(data, kind)


# --- clamd ---------------------------------------------------------------------------------------


@pytest.fixture
def clamd() -> Iterator[tuple[int, list[bytes], list[bytes]]]:
    """A one-shot-per-connection INSTREAM server; ``answers`` are popped in order."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    received: list[bytes] = []
    answers: list[bytes] = []

    def serve() -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            with conn:
                command = b""
                while not command.endswith(b"\0"):
                    command += conn.recv(1)
                data = b""
                while True:
                    (size,) = struct.unpack("!L", conn.recv(4, socket.MSG_WAITALL))
                    if size == 0:
                        break
                    data += conn.recv(size, socket.MSG_WAITALL)
                received.append(data)
                conn.sendall(answers.pop(0) if answers else b"stream: OK\0")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield server.getsockname()[1], received, answers
    server.close()


def test_r5_clean_and_infected_answers(clamd: tuple[int, list[bytes], list[bytes]]) -> None:
    port, received, answers = clamd
    scanner = ClamdScanner(host="127.0.0.1", port=port, timeout_seconds=5)
    big = b"x" * (200 * 1024)  # several chunks
    assert scanner.scan(big).clean is True
    assert received == [big]
    answers.append(b"stream: Eicar-Test-Signature FOUND\0")
    result = scanner.scan(b"y")
    assert (result.clean, result.signature) == (False, "Eicar-Test-Signature")


def test_r5_an_error_answer_or_no_daemon_is_unavailable_never_clean(
    clamd: tuple[int, list[bytes], list[bytes]],
) -> None:
    port, _, answers = clamd
    answers.append(b"INSTREAM size limit exceeded. ERROR\0")
    with pytest.raises(ScannerUnavailable):
        ClamdScanner(host="127.0.0.1", port=port, timeout_seconds=5).scan(b"z")
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    free = closed.getsockname()[1]
    closed.close()
    with pytest.raises(ScannerUnavailable):
        ClamdScanner(host="127.0.0.1", port=free, timeout_seconds=1).scan(b"z")
