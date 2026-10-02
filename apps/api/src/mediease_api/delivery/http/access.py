"""Access policy on every route — default deny (FR-AUTH-03; spec R6, R7, R10).

Every view declares one policy with a decorator:

| Decorator | Who may call it | Context available in the view |
|---|---|---|
| ``@public`` | anyone, no session | none |
| ``@authenticated`` | any signed-in user | ``current_principal()`` |
| ``@clinic(Permission.X)`` | a member of the clinic who holds ``X`` | ``current_context()`` |
| ``@ops`` | platform ops users (``is_platform_ops``) | ``current_principal()`` |

One ``before_request`` hook enforces them, so a route is protected by
declaring its policy, not by remembering to call a check. Two safety nets make
"every route" true by construction rather than by review:
``check_every_route_has_policy`` fails ``create_app`` when any registered
route has no policy, and a route that somehow reaches the hook without one
raises ``MissingAccessPolicy`` (→ 500) instead of being served.

The hook binds ``user_id`` and ``clinic_id`` into the log context for the rest
of the request, and stores the ``RequestContext`` so views can pass it into
use cases — application code never reads Flask globals (apps/api/CLAUDE.md).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import structlog
from flask import Flask, g, request
from structlog.contextvars import bind_contextvars

from mediease_api.application.auth.authenticate import AuthenticateRequest, resolve_clinic
from mediease_api.application.auth.errors import PermissionDenied
from mediease_api.application.context import Principal, RequestContext
from mediease_api.delivery.http.session_cookies import ACCESS_COOKIE
from mediease_api.delivery.middleware import get_request_id
from mediease_api.domain.identity.permissions import Permission

logger = structlog.get_logger(__name__)

# Which clinic a request is for, when the user works in more than one (R6).
CLINIC_HEADER = "X-Clinic-ID"

_POLICY_ATTR = "_mediease_access_policy"
_PRINCIPAL = "mediease_principal"
_CONTEXT = "mediease_request_context"


class Access(StrEnum):
    PUBLIC = "PUBLIC"
    AUTHENTICATED = "AUTHENTICATED"
    CLINIC = "CLINIC"
    OPS = "OPS"


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    access: Access
    # Set for CLINIC policies only: the permission the endpoint needs.
    permission: Permission | None = None


class MissingAccessPolicy(RuntimeError):
    """Routes without a declared policy. A programming error, never a client's fault."""

    def __init__(self, endpoints: Iterable[str]) -> None:
        listed = ", ".join(sorted(endpoints))
        super().__init__(
            f"no access policy on: {listed}. Decorate the view with @public, "
            "@authenticated, @clinic(Permission.X) or @ops."
        )


# --- Declaring a policy ----------------------------------------------------------------------
# The decorators only tag the function and return it unchanged, so Flask still
# registers the original view (name, signature and annotations intact).


def _tagged[ViewT: Callable[..., object]](view: ViewT, policy: AccessPolicy) -> ViewT:
    setattr(view, _POLICY_ATTR, policy)
    return view


def public[ViewT: Callable[..., object]](view: ViewT) -> ViewT:
    """No session needed: health, readiness, sign-in."""
    return _tagged(view, AccessPolicy(Access.PUBLIC))


def authenticated[ViewT: Callable[..., object]](view: ViewT) -> ViewT:
    """A signed-in user, without choosing a clinic (``/me``)."""
    return _tagged(view, AccessPolicy(Access.AUTHENTICATED))


def ops[ViewT: Callable[..., object]](view: ViewT) -> ViewT:
    """Platform ops only (R10); clinic staff are refused even as owners."""
    return _tagged(view, AccessPolicy(Access.OPS))


def clinic[ViewT: Callable[..., object]](permission: Permission) -> Callable[[ViewT], ViewT]:
    """A member of the request's clinic who holds ``permission`` (PRD §8.1)."""

    def decorate(view: ViewT) -> ViewT:
        return _tagged(view, AccessPolicy(Access.CLINIC, permission))

    return decorate


def policy_of(view: Callable[..., object]) -> AccessPolicy | None:
    policy = getattr(view, _POLICY_ATTR, None)
    return policy if isinstance(policy, AccessPolicy) else None


# --- Reading the result in a view ------------------------------------------------------------


def current_principal() -> Principal:
    """The authenticated caller. Only on ``@authenticated``, ``@clinic`` and ``@ops`` routes."""
    principal = g.get(_PRINCIPAL)
    if not isinstance(principal, Principal):
        raise RuntimeError("no principal on this request: is the route @authenticated?")
    return principal


def current_context() -> RequestContext:
    """The request's clinic context. Only on ``@clinic`` routes."""
    context = g.get(_CONTEXT)
    if not isinstance(context, RequestContext):
        raise RuntimeError("no request context: is the route @clinic(...)?")
    return context


# --- Enforcement -----------------------------------------------------------------------------


class Authenticator(Protocol):
    """What the hook needs from the composition root: a fresh use case per request."""

    def authenticate(self) -> AuthenticateRequest: ...


def register_access_control(app: Flask, authenticator: Authenticator) -> None:
    """Enforce each route's policy before it runs (registered after the CSRF hook)."""

    @app.before_request
    def _enforce_access_policy() -> None:
        if request.endpoint is None:
            return  # no route matched: dispatch answers 404 REQ_NOT_FOUND
        policy = policy_of(app.view_functions[request.endpoint])
        if policy is None:
            raise MissingAccessPolicy([request.endpoint])
        if policy.access is Access.PUBLIC:
            return

        principal = authenticator.authenticate().execute(request.cookies.get(ACCESS_COOKIE))
        setattr(g, _PRINCIPAL, principal)
        bind_contextvars(user_id=str(principal.user_id))

        if policy.access is Access.AUTHENTICATED:
            return
        if policy.access is Access.OPS:
            if not principal.is_platform_ops:
                logger.info("perm.denied", reason="not_platform_ops", route=request.endpoint)
                raise PermissionDenied()
            return

        access = resolve_clinic(principal, request.headers.get(CLINIC_HEADER))
        context = RequestContext.of(principal, access, request_id=get_request_id())
        assert policy.permission is not None  # a CLINIC policy always carries one
        context.require(policy.permission)
        setattr(g, _CONTEXT, context)
        bind_contextvars(clinic_id=str(context.clinic_id))


def check_every_route_has_policy(app: Flask) -> None:
    """Fail at start-up if any registered route is unprotected (default deny)."""
    missing = [
        endpoint
        for endpoint, view in app.view_functions.items()
        if policy_of(view) is None and endpoint != "static"
    ]
    if missing:
        raise MissingAccessPolicy(missing)
