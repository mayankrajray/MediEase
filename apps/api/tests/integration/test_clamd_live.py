"""The real ClamAV daemon (M7b-P7; NFR-20; journey 5): EICAR is found, a clean file passes.

Runs against the compose ``clamav`` service on ``127.0.0.1:3310`` (``CLAMD_TEST_HOST`` and
``CLAMD_TEST_PORT`` override); skipped when no daemon answers, e.g. on a machine without the stack.
The EICAR test string is assembled at run time so no antivirus quarantines this file.
"""

from __future__ import annotations

import os

import pytest

from mediease_api.adapters.malware.clamd import ClamdScanner

SCANNER = ClamdScanner(
    host=os.environ.get("CLAMD_TEST_HOST", "127.0.0.1"),
    port=int(os.environ.get("CLAMD_TEST_PORT", "3310")),
    timeout_seconds=30,
)

pytestmark = pytest.mark.skipif(not SCANNER.ping(), reason="no clamd on the test host")


def eicar() -> bytes:
    parts = [r"X5O!P%@AP[4\PZX54(P^)7CC)7}$", "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!", "$H+H*"]
    return "".join(parts).encode("ascii")


def test_nfr_20_clamd_finds_eicar() -> None:
    result = SCANNER.scan(eicar())
    assert result.clean is False and result.signature and "Eicar" in result.signature


def test_nfr_20_clamd_passes_a_clean_pdf() -> None:
    assert SCANNER.scan(b"%PDF-1.7\n%clean synthetic file\n").clean is True
