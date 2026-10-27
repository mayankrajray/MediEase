"""Upload errors (spec prescription-uploads §10; docs/ERRORS.md "Prescription uploads")."""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError


class UploadFileRejected(DomainError):
    """R1: not a PDF, JPEG or PNG by its bytes, empty, or over 10 MB (``details.reason``)."""

    code = "UPL_FILE_REJECTED"

    def __init__(self, reason: str) -> None:
        super().__init__("Upload a PDF, JPEG or PNG of at most 10 MB.", reason=reason)


class UploadRateLimited(DomainError):
    """R2: too many uploads or codes from this account or caller this hour."""

    code = "UPL_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many uploads. Please try again later.")
        self.retry_after_seconds = retry_after_seconds


class TooManyUploads(DomainError):
    """R2: three of this account's uploads are still being checked."""

    code = "UPL_TOO_MANY"

    def __init__(self) -> None:
        super().__init__("Please wait for your other uploads to finish.")


class UploadFailed(DomainError):
    """The file could not be stored; nothing was kept."""

    code = "UPL_UPLOAD_FAILED"

    def __init__(self) -> None:
        super().__init__("The upload could not be saved. Please try again.")


class ChallengeFailed(DomainError):
    """R12: wrong digits, or nothing to check them against: the same answer either way."""

    code = "UPL_CHALLENGE_FAILED"

    def __init__(self, attempts_left: int) -> None:
        super().__init__(
            "Those digits do not match the clinic's records for this prescription.",
            attempts_left=str(attempts_left),
        )
        self.attempts_left = attempts_left


class NotAwaitingChallenge(DomainError):
    code = "UPL_NOT_AWAITING"

    def __init__(self) -> None:
        super().__init__("This upload is not waiting for the phone digits.")


class NotVerified(DomainError):
    code = "UPL_NOT_VERIFIED"

    def __init__(self) -> None:
        super().__init__("This upload has not been verified.")


class SelectionRequired(DomainError):
    """R15, R16: a superseded upload needs the user's choice before the assistant uses it."""

    code = "UPL_SELECTION_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Choose the version you uploaded or the latest one first.")
