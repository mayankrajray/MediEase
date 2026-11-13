"""Every API setting reaches the containers (M9-P1).

docker-compose.yml passes the settings explicitly (x-api-environment), so a setting missing from
that list silently keeps its default inside the containers. PUBLIC_BASE_URL was missing: harmless
locally, where the default is valid, and fatal in production (CFG_INVALID: must use https).
"""

from __future__ import annotations

import re
from pathlib import Path

from mediease_api.config.settings import AppSettings

COMPOSE = Path(__file__).resolve().parents[5] / "docker-compose.yml"


def _passed() -> set[str]:
    text = COMPOSE.read_text(encoding="utf-8-sig")
    block = text.split("x-api-environment: &api-environment", 1)[1].split("\nx-", 1)[0]
    return set(re.findall(r"^  ([A-Z][A-Z0-9_]+):", block, re.MULTILINE))


def test_m9_p1_compose_passes_every_api_setting_and_nothing_else() -> None:
    passed = _passed()
    assert set(AppSettings.model_fields) - passed == set(), "add these to x-api-environment"
    assert passed - set(AppSettings.model_fields) == set(), "not settings the API reads"
