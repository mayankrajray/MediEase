"""scripts/inspect_link_token.py prints a token offline and refuses anything else (M4-P5)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.unit.domain.test_links import a_link, claims_of, link_token

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "inspect_link_token.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_it_prints_the_claims_of_a_token_or_a_link_url() -> None:
    link = a_link()
    token = link_token(claims_of(link))
    for given in (token, f"https://app.example.test/p/{token}?lang=hi"):
        done = _run(given)
        assert done.returncode == 0, done.stderr
        assert f"jti: {link.id}" in done.stdout
        assert "signature: not checked" in done.stdout


def test_it_refuses_what_is_not_a_token() -> None:
    done = _run("hello")
    assert done.returncode == 1 and "not a MediEase patient link token" in done.stderr
    assert _run().returncode == 2
