"""Patient codes: ``<prefix>-<sequence>``, e.g. ``ME-0142`` (FR-PAT-03, spec R4).

The prefix belongs to the clinic (2-4 upper-case letters), the sequence counts up
per clinic and is never reused. The counter itself lives on ``Clinic``; this module
only knows the shape.
"""

from __future__ import annotations

import re

from mediease_api.domain.shared.errors import InvalidValue

MIN_SEQUENCE_DIGITS = 4
DEFAULT_PREFIX = "CL"

_PREFIX = re.compile(r"[A-Z]{2,4}")
_CODE = re.compile(r"([A-Z]{2,4})-(\d{4,})")
# What a person types into search: letters, an optional hyphen, digits ("me-142", "ME0142").
_CODE_QUERY = re.compile(r"([A-Za-z]{2,4})-?(\d{1,9})")
_WORD = re.compile(r"[A-Za-z]+")


def validate_code_prefix(prefix: str) -> str:
    if not _PREFIX.fullmatch(prefix):
        raise InvalidValue("patient_code_prefix", "must be 2-4 upper-case letters")
    return prefix


def derive_code_prefix(clinic_name: str) -> str:
    """A prefix from the clinic's name: word initials, else its first letters, else ``CL``.

    "Sample Clinic" -> ``SC``; "Apollo" -> ``AP``; a name with no Latin letters -> ``CL``.
    Ops can choose a different one when creating the clinic (P2).
    """
    words = _WORD.findall(clinic_name)
    initials = "".join(word[0] for word in words[:4]).upper()
    if len(initials) >= 2:
        return initials
    letters = "".join(words).upper()
    return letters[:2] if len(letters) >= 2 else DEFAULT_PREFIX


def format_code(prefix: str, sequence: int) -> str:
    """``ME`` and 142 -> ``ME-0142``; the number grows past four digits instead of wrapping."""
    if sequence < 1:
        raise InvalidValue("patient_code", "the sequence starts at 1")
    return f"{validate_code_prefix(prefix)}-{sequence:0{MIN_SEQUENCE_DIGITS}d}"


def validate_code(code: str) -> str:
    if not _CODE.fullmatch(code):
        raise InvalidValue("code", "must look like ME-0142")
    return code


def parse_code_query(text: str) -> str | None:
    """A search text in code form as the canonical code (``me-142`` -> ``ME-0142``), or ``None``."""
    match = _CODE_QUERY.fullmatch(text.strip())
    if match is None:
        return None
    letters, digits = match.groups()
    return f"{letters.upper()}-{int(digits):0{MIN_SEQUENCE_DIGITS}d}"
