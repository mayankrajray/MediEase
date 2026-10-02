"""Who is acting, and where — the result of authenticating and authorising a request.

``Principal`` is what a valid access token proves after the per-request checks
(spec R7): an active user, a live session, and the clinics they may work in.
It is clinic-independent, which is all ``/me`` and ops routes need.

``RequestContext`` adds the one clinic this request is for (R6) and the
permissions the member holds there, and is passed explicitly into use cases —
application code never reads Flask globals (apps/api/CLAUDE.md "Patterns").

Nothing here does I/O: delivery builds a context once per request
(``delivery/http/access.py``) and hands it on.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from mediease_api.application.auth.errors import PermissionDenied
from mediease_api.domain.identity.access import ClinicAccess
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.identity.user import User


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated caller: the user, their session and their clinic access."""

    user: User
    # The refresh-token family the access token was issued for (its `sid`).
    session_id: UUID
    access: tuple[ClinicAccess, ...]

    @property
    def user_id(self) -> UUID:
        return self.user.id

    @property
    def is_platform_ops(self) -> bool:
        return self.user.is_platform_ops


@dataclass(frozen=True, slots=True)
class RequestContext:
    """One request, one user, one clinic (ADR-0003). Built by delivery, used by use cases."""

    request_id: str | None
    user_id: UUID
    session_id: UUID
    clinic_id: UUID
    membership_id: UUID
    role: Role
    permissions: frozenset[Permission]

    @classmethod
    def of(
        cls, principal: Principal, access: ClinicAccess, *, request_id: str | None
    ) -> RequestContext:
        return cls(
            request_id=request_id,
            user_id=principal.user_id,
            session_id=principal.session_id,
            clinic_id=access.clinic_id,
            membership_id=access.membership_id,
            role=access.role,
            permissions=access.permissions,
        )

    def allows(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, permission: Permission) -> None:
        """Enforce one permission; the endpoint declares which (FR-AUTH-03)."""
        if not self.allows(permission):
            raise PermissionDenied(permission=permission.value, role=self.role.value)
