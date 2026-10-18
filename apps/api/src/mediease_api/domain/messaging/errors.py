"""Messaging error codes (docs/ERRORS.md "Reminders and messaging"; spec R7).

A provider either *refused* a message, so we know it was not sent, or the outcome is *unknown*
(a timeout, a dropped connection after the request left). Only a refusal may be retried: a
second call after an unknown outcome could deliver the same message twice (decision 4A,
at most once).
"""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError

# The provider refused for now; retried with the job back-off (R7).
MSG_PROVIDER_RATE_LIMIT = "MSG_PROVIDER_RATE_LIMIT"
MSG_PROVIDER_UNAVAILABLE = "MSG_PROVIDER_UNAVAILABLE"
# The provider refused for good (R7).
MSG_TEMPLATE_NOT_FOUND = "MSG_TEMPLATE_NOT_FOUND"
MSG_TEMPLATE_PARAMS = "MSG_TEMPLATE_PARAMS"
MSG_RECIPIENT_INVALID = "MSG_RECIPIENT_INVALID"
# We cannot tell whether the provider accepted it; never sent again (decision 4A).
MSG_OUTCOME_UNKNOWN = "MSG_OUTCOME_UNKNOWN"
# M5-P3: the provider refused our credentials (token expired, permission removed), or refused the
# message for a reason we have no better code for. Neither is retried.
MSG_PROVIDER_AUTH = "MSG_PROVIDER_AUTH"
MSG_PROVIDER_REJECTED = "MSG_PROVIDER_REJECTED"
# A message row that was prepared, refused, and no longer applies at its retry.
MSG_NO_CONSENT = "MSG_NO_CONSENT"
MSG_NOT_APPLICABLE = "MSG_NOT_APPLICABLE"

RETRYABLE_CODES = frozenset({MSG_PROVIDER_RATE_LIMIT, MSG_PROVIDER_UNAVAILABLE})


class ProviderRefused(Exception):
    """The provider said no; nothing was sent. ``retryable`` follows the code (R7)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = code in RETRYABLE_CODES

    def __str__(self) -> str:
        return self.code


class ProviderOutcomeUnknown(Exception):
    """The request may or may not have been accepted (timeout, connection lost)."""

    code = MSG_OUTCOME_UNKNOWN

    def __str__(self) -> str:
        return self.code


class TemplateParamsInvalid(Exception):
    """Variables do not match the template's schema (R8). The message names no value."""

    code = MSG_TEMPLATE_PARAMS

    def __init__(self, template_key: str, reason: str) -> None:
        super().__init__(f"{template_key}: {reason}")
        self.template_key = template_key
        self.reason = reason


# --- Webhooks (M5-P3; spec R12, R13, AC6) -------------------------------------------------------

# A status that matches no message yet (it can arrive before our write commits); retried, then
# recorded on the event.
WH_UNMATCHED = "WH_UNMATCHED"
# An event of a kind we do not handle (stored and marked processed).
WH_UNKNOWN_EVENT = "WH_UNKNOWN_EVENT"


class WebhookSignatureInvalid(DomainError):
    """R13, AC6: the body is not signed with our app secret. Nothing is stored."""

    code = "WH_SIGNATURE_INVALID"

    def __init__(self) -> None:
        super().__init__("The webhook signature is not valid.")


class WebhookVerifyFailed(DomainError):
    """R12: the subscription challenge did not carry our verify token."""

    code = "WH_VERIFY_FAILED"

    def __init__(self) -> None:
        super().__init__("The webhook verification request was refused.")


class WebhookRateLimited(DomainError):
    code = "WH_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many requests. Please wait a moment.")
        self.retry_after_seconds = retry_after_seconds
