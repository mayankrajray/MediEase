"""Ports the assistant needs besides the model (M7a-P3; ADR-0024)."""

from __future__ import annotations

from typing import Protocol


class ProposalSignerPort(Protocol):
    """Signs a proposal's bytes into an opaque token, and gets them back only if untouched."""

    def sign(self, payload: bytes) -> str: ...

    def open(self, token: str) -> bytes | None:
        """The signed bytes, or ``None`` for a token that was altered or not ours."""
        ...
