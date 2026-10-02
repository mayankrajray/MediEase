"""Fixtures for the application-layer tests (harness.py builds the use cases)."""

from __future__ import annotations

import pytest

from tests.unit.application.harness import Auth, build_auth


@pytest.fixture
def auth() -> Auth:
    return build_auth()
