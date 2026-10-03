"""Clinic administration errors (docs/ERRORS.md "Auth and permissions").

Onboarding and staff management refuse for reasons the caller can act on: a
slug somebody else took, a member who is already in this clinic, or an
invitation that is no longer usable. An invitation the API has never seen is
"invalid" (404); one it knows but cannot accept says why, because the invitee
holds the link and needs to know whether to ask for a new one.
"""

from __future__ import annotations

from mediease_api.domain.shared.errors import DomainError


class SlugTaken(DomainError):
    """Clinic slugs are unique across the platform: they appear in public URLs (M7)."""

    code = "CLN_SLUG_TAKEN"

    def __init__(self) -> None:
        super().__init__("That clinic URL is already taken. Choose another.")


class MemberExists(DomainError):
    """I2: this user already has a membership in this clinic (active or deactivated)."""

    code = "CLN_MEMBER_EXISTS"

    def __init__(self) -> None:
        super().__init__("This person is already a member of this clinic.")


class InviteInvalid(DomainError):
    """Unknown or malformed invitation secret. Answered as 404: nothing is revealed."""

    code = "CLN_INVITE_INVALID"

    def __init__(self) -> None:
        super().__init__("This invitation link is not valid.")


class InviteExpired(DomainError):
    code = "CLN_INVITE_EXPIRED"

    def __init__(self) -> None:
        super().__init__("This invitation has expired. Ask your clinic to invite you again.")


class InviteUsed(DomainError):
    code = "CLN_INVITE_USED"

    def __init__(self) -> None:
        super().__init__("This invitation has already been used. Sign in instead.")
