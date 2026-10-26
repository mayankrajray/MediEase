"""Tools are offered by permission and read their arguments strictly (M7a; spec assistant R6)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from mediease_api.application.assistant.engine import MessageRole, TurnMessage, check_messages
from mediease_api.application.assistant.staff import StaffToolbox
from mediease_api.application.assistant.tools import Args, ToolArgumentError
from mediease_api.application.context import RequestContext, RequestInfo
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.shared.errors import InvalidValue


def _ctx(permissions: frozenset[Permission]) -> RequestContext:
    return RequestContext(
        info=RequestInfo(),
        user_id=uuid4(),
        session_id=uuid4(),
        clinic_id=uuid4(),
        membership_id=uuid4(),
        role=Role.FRONT_DESK,
        permissions=permissions,
    )


def test_r6_only_tools_the_role_may_use_are_offered() -> None:
    box = StaffToolbox(
        use_cases=Any,
        ctx=_ctx(frozenset({Permission.APPOINTMENTS_MANAGE})),
        timezone="Asia/Kolkata",
    )  # type: ignore[arg-type]
    names = {t.name for t in box.tools()}
    assert "find_patient" not in names and "today_queue" in names
    none = StaffToolbox(use_cases=Any, ctx=_ctx(frozenset()), timezone="Asia/Kolkata")  # type: ignore[arg-type]
    assert none.tools() == []


def test_args_are_typed_and_bounded() -> None:
    args = Args(
        {
            "a": " x ",
            "n": "3",
            "f": "true",
            "u": "not-a-uuid",
            "t": "2026-10-27T10:00:00",
            "long": "y" * 300,
        }
    )
    assert args.text("a") == "x"
    assert args.number("n") == 3
    assert args.flag("f") is True
    assert args.text("missing", required=False) is None
    for bad in (
        lambda: args.uuid("u"),
        lambda: args.instant("t"),  # no time zone
        lambda: args.text("long"),
        lambda: args.required_text("missing"),
        lambda: args.number("n", maximum=2),
        lambda: Args({"f": "maybe"}).flag("f"),
        lambda: Args({"d": "27/10"}).day("d"),
    ):
        with pytest.raises(ToolArgumentError):
            bad()


def test_r3_message_limits() -> None:
    ok = [TurnMessage(MessageRole.USER, "hi")]
    check_messages(ok)
    for bad in (
        [],
        [TurnMessage(MessageRole.ASSISTANT, "hi")],
        [TurnMessage(MessageRole.USER, " ")],
    ):
        with pytest.raises(InvalidValue):
            check_messages(bad)
