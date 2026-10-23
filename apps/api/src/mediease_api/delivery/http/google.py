"""Google sign-in for staff and patients: ``/api/v1/auth/google/start`` and ``/callback``.

M6a-P3; FR-AUTH-07, FR-PRT-01; ADR-0015 decisions 3, 4, 6. Both are browser navigations, not
API calls, so they answer with redirects, never JSON:

- ``GET /start?intent=staff|patient&next=&login_hint=`` seals the flow into ``me_oidc`` (10
  minutes, HttpOnly, path ``/api/v1/auth/google``) and redirects to Google (or, with the fake
  provider, straight back to the callback).
- ``GET /callback?state=&code=`` (or ``error=``) finishes the sign-in, sets the staff or the
  portal cookies and redirects to ``next``. Any failure redirects to ``/sign-in`` or
  ``/portal/sign-in`` with a fixed ``reason`` the web app turns into a message; nothing from the
  query string is ever reflected.

``next`` is checked here as well as in the web app: a same-origin path only, inside the portal
for patients and outside it for staff, never a sign-in page.
"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import urlencode, urlsplit

from flask import Blueprint, Response, request

from mediease_api.application.auth.google import (
    CompleteGoogleSignIn,
    FailureReason,
    GoogleIntent,
    GoogleSignInFailed,
    StaffSignedIn,
    StartGoogleSignIn,
)
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.request_info import request_info
from mediease_api.delivery.http.session_cookies import (
    PORTAL_COOKIES,
    STAFF_COOKIES,
    set_session_cookies,
)

FLOW_COOKIE = "me_oidc"
FLOW_COOKIE_PATH = "/api/v1/auth/google"
_FLOW_MAX_AGE = 600
_MAX_NEXT_LENGTH = 512

_SIGN_IN_PAGE = {GoogleIntent.STAFF: "/sign-in", GoogleIntent.PATIENT: "/portal/sign-in"}
_LANDING = {GoogleIntent.STAFF: "/today", GoogleIntent.PATIENT: "/portal"}
_SIGN_IN_PAGES = ("/sign-in", "/portal/sign-in", "/portal/sign-up")


class GoogleUseCases(Protocol):
    def start_google_sign_in(self) -> StartGoogleSignIn: ...
    def complete_google_sign_in(self) -> CompleteGoogleSignIn: ...


def safe_next(raw: str | None, intent: GoogleIntent) -> str:
    """``raw`` if it is a same-origin path this kind of session may land on, else the default."""
    default = _LANDING[intent]
    if not raw or len(raw) > _MAX_NEXT_LENGTH:
        return default
    if not raw.startswith("/") or raw.startswith("//") or "\\" in raw:
        return default
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in raw):
        return default
    parts = urlsplit(raw)
    if parts.scheme or parts.netloc:
        return default
    path = parts.path
    if any(path == page or path.startswith(f"{page}/") for page in _SIGN_IN_PAGES):
        return default
    in_portal = path == "/portal" or path.startswith("/portal/")
    if in_portal is not (intent is GoogleIntent.PATIENT):
        return default
    return raw


def create_google_blueprint(use_cases: GoogleUseCases, *, cookie_secure: bool) -> Blueprint:
    bp = Blueprint("google", __name__, url_prefix="/api/v1/auth/google")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("/start")
    @public
    def start() -> Response:
        try:
            intent = GoogleIntent(request.args.get("intent", ""))
        except ValueError:
            return _failed(GoogleIntent.STAFF, FailureReason.FAILED)
        try:
            started = use_cases.start_google_sign_in().execute(
                intent,
                next_path=safe_next(request.args.get("next"), intent),
                login_hint=request.args.get("login_hint"),
                info=request_info(),
            )
        except GoogleSignInFailed as exc:
            return _failed(exc.intent, exc.reason)
        response = _redirect(started.authorization_url)
        response.set_cookie(
            FLOW_COOKIE,
            started.flow,
            max_age=_FLOW_MAX_AGE,
            path=FLOW_COOKIE_PATH,
            secure=cookie_secure,
            httponly=True,
            # Lax: the cookie must come back on Google's top-level redirect to the callback.
            samesite="Lax",
        )
        return response

    @bp.get("/callback")
    @public
    def callback() -> Response:
        try:
            outcome = use_cases.complete_google_sign_in().execute(
                flow=request.cookies.get(FLOW_COOKIE),
                state=request.args.get("state"),
                code=request.args.get("code"),
                error=request.args.get("error"),
                info=request_info(),
            )
        except GoogleSignInFailed as exc:
            response = _failed(exc.intent, exc.reason)
        else:
            response = _redirect(outcome.next_path)
            if isinstance(outcome, StaffSignedIn):
                set_session_cookies(
                    response, outcome.session.tokens, secure=cookie_secure, cookies=STAFF_COOKIES
                )
            else:
                set_session_cookies(
                    response, outcome.session.tokens, secure=cookie_secure, cookies=PORTAL_COOKIES
                )
        # One flow, one use: whatever happened, the flow cookie is spent.
        response.delete_cookie(
            FLOW_COOKIE, path=FLOW_COOKIE_PATH, secure=cookie_secure, httponly=True, samesite="Lax"
        )
        return response

    return bp


def _redirect(location: str) -> Response:
    return Response(status=302, headers={"Location": location})


def _failed(intent: GoogleIntent, reason: FailureReason) -> Response:
    return _redirect(f"{_SIGN_IN_PAGE[intent]}?{urlencode({'reason': reason.value})}")
