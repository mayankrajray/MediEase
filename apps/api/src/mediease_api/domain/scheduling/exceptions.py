"""Date exceptions to a weekly schedule (spec R17, R18; decision D8).

``LEAVE`` is a whole day off for one doctor; at most one per doctor and date. ``EXTRA`` adds one
block on one date, validated like a weekly block. A part-day absence is a leave plus an extra for
the hours the doctor does work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from mediease_api.domain.scheduling.blocks import BlockShape
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.shared.text import optional_text
from mediease_api.domain.shared.time import require_utc


class ExceptionKind(StrEnum):
    LEAVE = "LEAVE"
    EXTRA = "EXTRA"


@dataclass(slots=True)
class ScheduleException:
    """A leave or an extra session on one clinic-local date. ``shape`` is set for EXTRA only."""

    id: UUID
    clinic_id: UUID
    doctor_id: UUID
    on_date: date
    kind: ExceptionKind
    shape: BlockShape | None
    note: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def leave(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        doctor_id: UUID,
        on_date: date,
        now: datetime,
        note: str | None = None,
    ) -> ScheduleException:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            on_date=on_date,
            kind=ExceptionKind.LEAVE,
            shape=None,
            note=optional_text(note, "note", max_length=200),
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def extra(
        cls,
        *,
        id: UUID,
        clinic_id: UUID,
        doctor_id: UUID,
        on_date: date,
        shape: BlockShape,
        mode: BookingMode,
        now: datetime,
        note: str | None = None,
    ) -> ScheduleException:
        now = require_utc(now, "now")
        return cls(
            id=id,
            clinic_id=clinic_id,
            doctor_id=doctor_id,
            on_date=on_date,
            kind=ExceptionKind.EXTRA,
            shape=shape.validate(mode),
            note=optional_text(note, "note", max_length=200),
            created_at=now,
            updated_at=now,
        )


def check_editable_date(on_date: date, *, today: date, horizon: date) -> date:
    """Exceptions are for the clinic's today up to the generation horizon (R18)."""
    if on_date < today:
        raise InvalidValue("on_date", "must be today or later in the clinic's time zone")
    if on_date > horizon:
        raise InvalidValue("on_date", "must be at most 180 days ahead")
    return on_date
