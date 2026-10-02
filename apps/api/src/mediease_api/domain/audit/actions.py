"""The catalogue of audited actions (FR-AUD-01, spec §7).

One closed set, so a typo cannot invent an action name and "where is
``staff.role_changed`` written?" is a single grep. Names follow the log
convention ``area.past_tense`` (apps/api/CLAUDE.md), because an audit action
is always something that already happened.

Actions are added in the phase that first writes them; M1-P4 covers the
session events and the staff role change. Staff invites, deactivations and
clinic creation arrive with their use cases in M1-P5.
"""

from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    AUTH_SIGNED_IN = "auth.signed_in"
    # Only for a known account: the unknown-identifier path has no lockout, so
    # auditing it would let an anonymous caller grow the table without bound.
    AUTH_SIGN_IN_FAILED = "auth.sign_in_failed"
    AUTH_SIGNED_OUT = "auth.signed_out"
    # A rotated refresh token was presented again: possible token theft (R5).
    AUTH_REFRESH_REUSED = "auth.refresh_reused"
    STAFF_ROLE_CHANGED = "staff.role_changed"
