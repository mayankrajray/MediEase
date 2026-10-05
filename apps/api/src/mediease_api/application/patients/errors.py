"""Patient errors raised by use cases (docs/ERRORS.md "Patients")."""

from __future__ import annotations

from collections.abc import Sequence

from mediease_api.application.patients.views import CandidateView
from mediease_api.domain.shared.errors import DomainError

MAX_CANDIDATES = 10


class PhoneExists(DomainError):
    """R2: patients already use this number. Carries who, so the front desk can choose.

    ``candidates`` is read only by the HTTP error mapper, to build the response for the
    signed-in staff member. It is never part of the message or the log line.
    """

    code = "PAT_PHONE_EXISTS"

    def __init__(self, candidates: Sequence[CandidateView]) -> None:
        super().__init__("Patients already use this phone number.")
        self.candidates = tuple(candidates)


class ImportInvalid(DomainError):
    """R8: the import file as a whole cannot be read (header, size, encoding). Nothing imported.

    ``problems`` are fixed sentences naming columns or positions, never the file's text.
    Bad *rows* are not this error: they are listed in the report.
    """

    code = "PAT_IMPORT_INVALID"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("The import file cannot be read. Nothing was imported.")
        self.problems = tuple(problems)
