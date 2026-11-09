"""The staff assistant books only what can still be booked (M7c-P3; FR-AI-01; spec assistant R19).

The developer's own test (4 Nov 2026): the assistant offered a 3:55 AM session that had ended,
a full 10:00 AM session, and never asked which doctor. Synthetic data only; the clock is fixed at
10:30 AM clinic time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from mediease_api.application.appointments.views import SessionView
from mediease_api.application.assistant.staff import StaffToolbox, system_prompt
from mediease_api.application.assistant.tools import Args, Tool, ToolArgumentError
from mediease_api.application.context import RequestContext, RequestInfo
from mediease_api.domain.identity.membership import Role
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session, SessionStatus
from tests.fakes import FakeClock

TZ = "Asia/Kolkata"
TODAY = date(2026, 10, 27)
# 10:30 AM in Kolkata.
NOW = datetime(2026, 10, 27, 5, 0, tzinfo=UTC)
DOCTOR = uuid4()


def _ist(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, 27, hour, minute, tzinfo=UTC) - timedelta(hours=5, minutes=30)


def _session(
    start: datetime,
    end: datetime,
    *,
    mode: BookingMode = BookingMode.TOKENS,
    slot: int | None = None,
    capacity: int = 30,
    booked: int = 0,
    status: SessionStatus = SessionStatus.OPEN,
) -> Session:
    return Session(
        id=uuid4(),
        clinic_id=uuid4(),
        doctor_id=DOCTOR,
        on_date=TODAY,
        starts_at=start,
        ends_at=end,
        mode=mode,
        slot_minutes=slot,
        capacity=capacity,
        booked_count=booked,
        next_token=booked + 1,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


ENDED = _session(_ist(3, 55), _ist(4, 40), booked=1)
FULL = _session(_ist(10), _ist(13), capacity=12, booked=12)
OPEN = _session(_ist(13), _ist(13, 45), booked=21)
SLOTS = _session(_ist(10), _ist(11, 30), mode=BookingMode.SLOTS, slot=15, capacity=6)


@dataclass
class _ListSessions:
    views: list[SessionView]
    asked: list[tuple[date, UUID | None]] = field(default_factory=list)

    def execute(
        self, ctx: RequestContext, on_date: date, *, doctor_id: UUID | None = None
    ) -> list[SessionView]:
        self.asked.append((on_date, doctor_id))
        return self.views


@dataclass
class _Doctor:
    id: UUID
    display_name: str
    is_active: bool = True


@dataclass
class _Patient:
    full_name: str = "Asha Rao"
    code: str = "SC-0001"


class _UseCases:
    def __init__(self, views: list[SessionView]) -> None:
        self.sessions = _ListSessions(views)

    def list_sessions(self) -> _ListSessions:
        return self.sessions

    def list_doctors(self) -> Any:
        doctors = [_Doctor(DOCTOR, "Dr. Sample Doctor")]
        return type("L", (), {"execute": lambda _self, ctx: doctors})()

    def get_patient(self) -> Any:
        return type("G", (), {"execute": lambda _self, ctx, pid: _Patient()})()


def _box(*sessions: Session) -> tuple[StaffToolbox, _UseCases]:
    uc = _UseCases([SessionView(s, frozenset()) for s in sessions])
    ctx = RequestContext(
        info=RequestInfo(),
        user_id=uuid4(),
        session_id=uuid4(),
        clinic_id=uuid4(),
        membership_id=uuid4(),
        role=Role.FRONT_DESK,
        permissions=frozenset(Permission),
    )
    box = StaffToolbox(use_cases=uc, ctx=ctx, timezone=TZ, clock=FakeClock(NOW))  # type: ignore[arg-type]
    return box, uc


def _tool(box: StaffToolbox, name: str) -> Tool:
    return next(t for t in box.tools() if t.name == name)


def _list(box: StaffToolbox, **args: Any) -> Any:
    tool = _tool(box, "list_sessions")
    assert tool.run is not None
    return tool.run(Args({"date": TODAY.isoformat(), **args}))


def test_fr_ai_01_list_sessions_hides_ended_full_and_closed_sessions() -> None:
    closed = _session(_ist(14), _ist(15), status=SessionStatus.CLOSED)
    box, _ = _box(ENDED, FULL, OPEN, closed)
    result = _list(box)
    ids = [s["session_id"] for s in result.data["sessions"]]
    assert ids == [str(OPEN.id)]
    assert "3:55 AM" not in result.summary and "1:00 PM" in result.summary
    assert "3 ended, closed or full sessions are not shown" in result.summary


def test_fr_ai_01_list_sessions_offers_only_slots_not_yet_over() -> None:
    box, _ = _box(SLOTS)
    [session] = _list(box).data["sessions"]
    starts = [datetime.fromisoformat(t) for t in session["free_slots"]]
    # 10:00 and 10:15 are over at 10:30; 10:30 to 11:15 remain.
    assert starts == [_ist(10, 30), _ist(10, 45), _ist(11), _ist(11, 15)]


def test_fr_ai_01_list_sessions_says_when_nothing_is_left() -> None:
    box, _ = _box(ENDED, FULL)
    result = _list(box)
    assert result.data["sessions"] == []
    assert "No session can still be booked that day" in result.summary


def test_fr_ai_01_list_sessions_refuses_a_past_date_and_passes_the_doctor() -> None:
    box, uc = _box(OPEN)
    with pytest.raises(ToolArgumentError, match="date has passed"):
        _list(box, date=(TODAY - timedelta(days=1)).isoformat())
    _list(box, doctor_id=str(DOCTOR))
    assert uc.sessions.asked[-1] == (TODAY, DOCTOR)


def _prepare(box: StaffToolbox, session: Session, slot: datetime | None = None) -> Any:
    tool = _tool(box, "book_appointment")
    assert tool.prepare is not None
    args: dict[str, Any] = {
        "patient_id": str(uuid4()),
        "session_id": str(session.id),
        "date": TODAY.isoformat(),
    }
    if slot is not None:
        args["slot_start"] = slot.isoformat()
    return tool.prepare(Args(args))


def test_fr_ai_01_an_ended_session_is_refused_before_the_confirmation() -> None:
    box, _ = _box(ENDED, OPEN)
    with pytest.raises(ToolArgumentError, match="already ended"):
        _prepare(box, ENDED)
    assert "1:00 PM" in _prepare(box, OPEN).summary


def test_fr_ai_01_a_slot_that_is_over_is_refused_before_the_confirmation() -> None:
    box, _ = _box(SLOTS)
    with pytest.raises(ToolArgumentError, match="already passed"):
        _prepare(box, SLOTS, _ist(10, 15))
    assert "10:45 AM" in _prepare(box, SLOTS, _ist(10, 45)).summary


def test_fr_ai_01_the_prompt_asks_which_doctor_only_when_there_are_several() -> None:
    one = system_prompt("2026-10-27 (Tuesday)", "Sample Clinic", doctors=[("Dr. A", "1")])
    assert "do not ask which doctor" in one
    two = system_prompt(
        "2026-10-27 (Tuesday)",
        "Sample Clinic",
        tomorrow="2026-10-28 (Wednesday)",
        doctors=[("Dr. A", "1"), ("Dr. B", "2")],
    )
    assert "ask which doctor before" in two and "Dr. B (doctor_id 2)" in two
    assert "tomorrow is 2026-10-28 (Wednesday)" in two
    assert "Hinglish" in two
