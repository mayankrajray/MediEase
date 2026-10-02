"""Text field rules shared by entities: trimmed, non-empty where required, bounded."""

from __future__ import annotations

from mediease_api.domain.shared.errors import InvalidValue


def required_text(value: str, field: str, *, max_length: int) -> str:
    """Return ``value`` trimmed; reject empty or over-long values."""
    cleaned = value.strip()
    if not cleaned:
        raise InvalidValue(field, "must not be empty")
    if len(cleaned) > max_length:
        raise InvalidValue(field, f"must be at most {max_length} characters")
    return cleaned


def optional_text(value: str | None, field: str, *, max_length: int) -> str | None:
    """Like ``required_text``, but ``None`` and blank values become ``None``."""
    if value is None or not value.strip():
        return None
    return required_text(value, field, max_length=max_length)
