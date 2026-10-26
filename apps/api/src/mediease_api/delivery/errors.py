"""HTTP error handling — the stable error envelope (CLAUDE.md "Observability").

Every API error returns:

    { "error": { "code", "message", "request_id", "details" } }

Codes are catalogued in ``docs/ERRORS.md``. Domain and application errors
(``DomainError``) get the status in ``DOMAIN_ERROR_STATUS``. Readiness
failures become a 503 with their ``READY_*`` code. Unhandled exceptions become
a single ``SYS_UNEXPECTED`` 500 with no stack trace in the body; the trace is
logged server-side with the same ``request_id``, so the failure is traceable
without leaking internals to the client.
"""

from __future__ import annotations

import re
from typing import Any

import structlog
from flask import Flask, Response, jsonify
from werkzeug.exceptions import HTTPException

from mediease_api.application.auth.errors import AccountLocked, AuthRateLimited
from mediease_api.application.clinics.errors import InvitesRateLimited
from mediease_api.application.patients.errors import ImportInvalid, PhoneExists
from mediease_api.delivery.http.bodies import candidate_body
from mediease_api.delivery.http.validation import RequestValidationFailed
from mediease_api.delivery.middleware import get_request_id
from mediease_api.domain.booking.request import BookingRateLimited
from mediease_api.domain.links.errors import LinkRateLimited
from mediease_api.domain.messaging.errors import WebhookRateLimited
from mediease_api.domain.onboarding.application import ApplicationRateLimited
from mediease_api.domain.prescriptions.errors import PdfBusy
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.ports.readiness import DatabaseTimeout, DatabaseUnavailable, ReadinessError

logger = structlog.get_logger(__name__)

SYS_UNEXPECTED = "SYS_UNEXPECTED"
_SYS_UNEXPECTED_MESSAGE = "An unexpected error occurred."

# Safe to show to staff and to monitoring; details live in the server log.
_READINESS_MESSAGES = {
    DatabaseUnavailable.code: "The database is not reachable.",
    DatabaseTimeout.code: "The database did not respond in time.",
}

# Framework HTTP errors with a catalogued code. Any other 4xx becomes
# REQ_<WERKZEUG_NAME> (e.g. REQ_UNSUPPORTED_MEDIA_TYPE); see docs/ERRORS.md.
_HTTP_CODES = {
    404: "REQ_NOT_FOUND",
    405: "REQ_METHOD_NOT_ALLOWED",
}

# Werkzeug headers worth keeping on the envelope response (405 must say what is allowed).
_PRESERVED_HEADERS = ("Allow", "Retry-After")

# HTTP status for every domain/application error code (docs/ERRORS.md). A code
# missing here is a programming error: it is logged and answered as a 500.
DOMAIN_ERROR_STATUS = {
    "REQ_VALIDATION_FAILED": 422,
    "REQ_NOT_FOUND": 404,
    "AUTH_INVALID_CREDENTIALS": 401,
    "AUTH_SESSION_EXPIRED": 401,
    "AUTH_REFRESH_REUSED": 401,
    "AUTH_LOCKED": 423,
    "AUTH_CSRF_INVALID": 403,
    "AUTH_ACCOUNT_DISABLED": 403,
    # M6a-P3: the portal and Google sign-in. The Google codes normally travel as a redirect
    # reason (delivery/http/google.py); the statuses apply if one ever reaches the envelope.
    "AUTH_RATE_LIMITED": 429,
    "AUTH_GOOGLE_FAILED": 400,
    "AUTH_GOOGLE_NO_STAFF_ACCOUNT": 403,
    "PRT_INVALID_CREDENTIALS": 401,
    "PRT_EMAIL_TAKEN": 409,
    # M6b-P1: linking a patient account to a clinic record.
    "PRT_INVITE_INVALID": 404,
    "PRT_ALREADY_LINKED": 409,
    "PRT_UNVERIFIED_ACCOUNT": 403,
    # M6b-P4: online booking requests and their soft hold.
    "PRT_TOO_MANY_REQUESTS": 409,
    "PRT_REQUEST_EXISTS": 409,
    "BKG_ALREADY_ANSWERED": 409,
    "PRT_RATE_LIMITED": 429,
    "APT_SLOT_HELD": 409,
    # M6c-P1: clinic applications (clinic-onboarding R7, R10, R12, R16).
    "ONB_RATE_LIMITED": 429,
    "ONB_FILE_REJECTED": 422,
    "ONB_CONFIRM_INVALID": 404,
    "ONB_UPLOAD_FAILED": 503,
    # M6c-P2 (R27, R29, R33): the review.
    "ONB_ALREADY_TAKEN": 409,
    "ONB_NOT_UNDER_REVIEW": 409,
    # M6c-P4 (R52, R53): the directory listing.
    "CLN_LISTING_BLOCKED": 409,
    "CLN_DOCTOR_NOT_VERIFIED": 409,
    # M6d-P1 (R3): the fee schedule.
    "BIL_SERVICE_NAME_TAKEN": 409,
    "BIL_TOO_MANY_SERVICES": 409,
    # M6d-P2 (R14-R26): bills and credit notes.
    "BIL_NOT_DRAFT": 409,
    "BIL_NOT_ISSUED": 409,
    "BIL_EMPTY": 409,
    "BIL_LINE_ALREADY_CREDITED": 409,
    "BIL_VISIT_BILLED": 409,
    "BIL_VISIT_NOT_COMPLETED": 409,
    "BIL_NOT_YOURS": 403,
    # M6d-P3 (R32-R36): payments and refunds.
    "BIL_PAYMENT_TOO_LARGE": 409,
    "BIL_VOID_TOO_LATE": 409,
    "BIL_ALREADY_VOIDED": 409,
    "BIL_VOID_REFUNDED": 409,
    # M6d-P4 (R43): a draft has no receipt.
    "BIL_RECEIPT_NOT_READY": 409,
    # M6b-P3b (R46): a dose outside its marking window.
    "PRT_DOSE_NOT_MARKABLE": 409,
    # M6a-P4: emailed verification and reset links.
    "AUTH_TOKEN_INVALID": 404,
    "AUTH_TOKEN_EXPIRED": 410,
    "PERM_DENIED": 403,
    "PERM_CLINIC_REQUIRED": 400,
    "CLN_SUSPENDED": 403,
    "CLN_LAST_OWNER": 409,
    "CLN_OWNER_REQUIRED": 409,
    "CLN_INVALID_TRANSITION": 409,
    "CLN_SLUG_TAKEN": 409,
    "CLN_MEMBER_EXISTS": 409,
    "CLN_INVITE_RATE_LIMITED": 429,
    "CLN_NO_DOCTOR_PROFILE": 409,
    "CLN_INVITE_INVALID": 404,
    "CLN_INVITE_EXPIRED": 410,
    "CLN_INVITE_USED": 410,
    "PAT_GUARDIAN_REQUIRED": 422,
    "PAT_PHONE_INVALID": 422,
    "PAT_PHONE_EXISTS": 409,
    "PAT_OPTED_OUT": 409,
    "PAT_NOT_OPTED_OUT": 409,
    "PAT_IMPORT_INVALID": 422,
    "SCH_INVALID_BLOCK": 422,
    "SCH_OVERLAP": 409,
    "SCH_LEAVE_EXISTS": 409,
    "SCH_MODE_INCOMPATIBLE": 409,
    "APT_SLOT_TAKEN": 409,
    "APT_SESSION_FULL": 409,
    "APT_SESSION_CLOSED": 409,
    "APT_OUTSIDE_SCHEDULE": 422,
    "APT_IN_PAST": 422,
    "APT_NOT_MODIFIABLE": 409,
    "APT_ALREADY_BOOKED": 409,
    "QUE_INVALID_TRANSITION": 409,
    "QUE_WRONG_TIME": 409,
    "QUE_NO_SESSION": 409,
    "VIS_ALREADY_EXISTS": 409,
    "VIS_NOT_STARTABLE": 409,
    "VIS_NOT_YOURS": 403,
    "VIS_LOCKED": 409,
    "VIS_STALE": 409,
    "VIS_NOT_COMPLETED": 409,
    # M6d-P6 (visit-attachments R2-R8): reports on visits.
    "VIS_FILE_REJECTED": 422,
    "VIS_ATTACHMENT_LIMIT": 409,
    "VIS_ATTACHMENT_NOT_YOURS": 403,
    "VIS_ATTACHMENT_LOCKED": 409,
    "VIS_UPLOAD_FAILED": 503,
    "RX_NOT_DRAFT": 409,
    "RX_EMPTY": 422,
    "RX_DOCTOR_INCOMPLETE": 422,
    "RX_STALE": 409,
    "RX_ALREADY_EXISTS": 409,
    "RX_DRAFT_EXISTS": 409,
    "RX_NOT_LATEST": 409,
    "RX_NOT_ISSUED": 409,
    "RX_PDF_BUSY": 503,
    "RX_PDF_FAILED": 500,
    "LINK_INVALID": 404,
    "LINK_EXPIRED": 410,
    "LINK_REVOKED": 410,
    "LINK_CHALLENGE_FAILED": 401,
    "LINK_LOCKED": 423,
    "LINK_CHALLENGE_REQUIRED": 401,
    "LINK_RATE_LIMITED": 429,
    "LINK_NOT_LOCKED": 409,
    "RX_NAME_TAKEN": 409,
    "RX_LIBRARY_FULL": 409,
    "WH_SIGNATURE_INVALID": 401,
    "WH_VERIFY_FAILED": 403,
    "WH_RATE_LIMITED": 429,
    "REM_NO_CONSENT": 409,
    "REM_IN_PAST": 422,
    "REM_CLINIC_PHONE_MISSING": 409,
    "REM_NOT_SCHEDULED": 409,
    "REM_FOLLOWS_APPOINTMENT": 409,
    "AUD_RANGE_TOO_LONG": 422,
}


def domain_error_response(exc: DomainError) -> tuple[Response, int]:
    """The envelope for a domain or application error, with its catalogued status."""
    status = DOMAIN_ERROR_STATUS.get(exc.code)
    if status is None:
        logger.error("app.unmapped_domain_error", code=SYS_UNEXPECTED, domain_code=exc.code)
        return error_response(SYS_UNEXPECTED, _SYS_UNEXPECTED_MESSAGE, 500)

    details: dict[str, Any] = dict(exc.details)
    if isinstance(exc, RequestValidationFailed):
        details = {"fields": exc.fields}
    elif isinstance(exc, InvalidValue):
        details = {"fields": [{"field": exc.field, "reason": exc.reason}]}
    elif isinstance(exc, PhoneExists):
        # For the signed-in staff member who asked (spec R2); never logged.
        details = {"candidates": [candidate_body(c) for c in exc.candidates]}
    elif isinstance(exc, ImportInvalid):
        details = {"problems": list(exc.problems)}
    response, _ = error_response(exc.code, exc.message, status, details)
    if isinstance(
        exc,
        AccountLocked
        | AuthRateLimited
        | PdfBusy
        | LinkRateLimited
        | WebhookRateLimited
        | InvitesRateLimited
        | BookingRateLimited
        | ApplicationRateLimited,
    ):
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
    return response, status


def error_response(
    code: str,
    message: str,
    status: int,
    details: dict[str, Any] | None = None,
) -> tuple[Response, int]:
    """Build a response in the stable error envelope."""
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(),
            "details": details or {},
        }
    }
    return jsonify(body), status


def _http_error_code(exc: HTTPException) -> str:
    status = exc.code or 500
    if status in _HTTP_CODES:
        return _HTTP_CODES[status]
    name = re.sub(r"[^A-Z0-9]+", "_", (exc.name or "HTTP error").upper()).strip("_")
    return f"REQ_{name}"


def register_error_handlers(app: Flask) -> None:
    """Attach the readiness, HTTP-exception and catch-all handlers to the app."""

    @app.errorhandler(ReadinessError)
    def _handle_readiness_error(exc: ReadinessError) -> tuple[Response, int]:
        # Degraded but handled (WARNING): the instance reports not-ready and the
        # orchestrator stops routing to it. The cause's type is logged for
        # diagnosis; its message is not (driver messages name hosts and users).
        cause = exc.__cause__
        logger.warning(
            "ready.check_failed",
            code=exc.code,
            cause=type(cause).__name__ if cause else None,
        )
        return error_response(exc.code, _READINESS_MESSAGES[exc.code], 503)

    @app.errorhandler(DomainError)
    def _handle_domain_error(exc: DomainError) -> tuple[Response, int]:
        # Expected outcomes (wrong password, not found, ...): the use case has
        # already logged the business event, so this is a DEBUG-level trace only.
        logger.debug("http.domain_error", code=exc.code)
        return domain_error_response(exc)

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException) -> tuple[Response, int]:
        status = exc.code or 500
        if status >= 500:
            # A framework-raised 5xx is still a server fault: same code and
            # generic message as an unhandled exception.
            logger.error("http.server_error", code=SYS_UNEXPECTED, status=status)
            return error_response(SYS_UNEXPECTED, _SYS_UNEXPECTED_MESSAGE, status)

        code = _http_error_code(exc)
        logger.info("http.client_error", code=code, status=status)
        response, _ = error_response(code, exc.description or exc.name, status)
        for name, value in exc.get_headers():
            if name in _PRESERVED_HEADERS:
                response.headers[name] = value
        return response, status

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception) -> tuple[Response, int]:
        logger.error("app.unexpected_error", code=SYS_UNEXPECTED, exc_info=exc)
        return error_response(SYS_UNEXPECTED, _SYS_UNEXPECTED_MESSAGE, 500)
