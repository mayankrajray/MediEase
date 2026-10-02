"""``GET /api/v1/me`` — who am I, and what may I do where (FR-AUTH-03).

No query of its own: authenticating the request already re-read the user and
every active membership (spec R7), so the answer is a view over the
``Principal``. That keeps the endpoint the web app polls after a refresh as
cheap as the authorisation it has already paid for.
"""

from __future__ import annotations

from dataclasses import dataclass

from mediease_api.application.auth.views import MembershipView, UserView
from mediease_api.application.context import Principal


@dataclass(frozen=True, slots=True)
class MeView:
    user: UserView
    memberships: tuple[MembershipView, ...]


def me_view(principal: Principal) -> MeView:
    return MeView(
        user=UserView.of(principal.user),
        memberships=tuple(MembershipView.of(a) for a in principal.access),
    )
