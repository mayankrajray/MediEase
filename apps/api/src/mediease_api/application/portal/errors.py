"""Portal sign-in errors (docs/ERRORS.md "Patient portal").

Like the staff ones, deliberately vague: none says whether an account exists or which part of
the credentials was wrong. ``PRT_EMAIL_TAKEN`` (sign-up) is the accepted exception, rate limited
(decision 7); it lives with the account in the domain.
"""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError


class PortalInvalidCredentials(DomainError):
    code = "PRT_INVALID_CREDENTIALS"

    def __init__(self) -> None:
        super().__init__("The email or password is incorrect.")


class PortalAccountDisabled(DomainError):
    """The account exists but is not active. Same code as staff; a patient's wording."""

    code = "AUTH_ACCOUNT_DISABLED"

    def __init__(self) -> None:
        super().__init__("This account is not active. Contact MediEase support.")
