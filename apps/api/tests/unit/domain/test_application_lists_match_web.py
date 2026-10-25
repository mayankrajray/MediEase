"""The web form's lists and reply promise equal the API's (M6c-P1; spec R4, R23, D3).

The form offers councils and specialties from ``apps/web/src/features/apply/lists.ts``; the API
accepts only its own lists. A difference would let the form offer a value the API refuses.
"""

from __future__ import annotations

import re
from pathlib import Path

from mediease_api.application.onboarding.email_templates import REPLY_PROMISE
from mediease_api.domain.onboarding.lists import COUNCILS, SPECIALTIES

WEB = (
    Path(__file__).resolve().parents[5] / "apps" / "web" / "src" / "features" / "apply" / "lists.ts"
)


def _array(source: str, name: str) -> list[str]:
    match = re.search(rf"export const {name}: readonly string\[\] = \[(.*?)\];", source, re.S)
    assert match is not None, f"{name} not found in {WEB}"
    return re.findall(r'"([^"]+)"', match.group(1))


def test_r4_the_councils_and_specialties_are_the_same_lists() -> None:
    source = WEB.read_text(encoding="utf-8")
    assert _array(source, "COUNCILS") == list(COUNCILS)
    assert _array(source, "SPECIALTIES") == list(SPECIALTIES)


def test_d3_the_reply_promise_is_the_same_words() -> None:
    source = WEB.read_text(encoding="utf-8")
    match = re.search(r'export const REPLY_PROMISE =\s*"([^"]+)";', source)
    assert match is not None
    assert match.group(1) == REPLY_PROMISE
