"""Reading and exporting the clinic's audit log (M6a-P8; FR-AUD-03, FR-AUD-01; decision 8A).

Owners only (``AUDIT_VIEW``). Ranges are whole days on the clinic's calendar, at most 92; with no
range the last 7 days. The list pages 50 at a time, newest first, by a keyset cursor. The export
returns every entry of the range up to 20,000 (more is refused: narrow the range), and is itself
audited (``audit.exported``: the range and the row count). Reading is not audited.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from mediease_api.application.audit import record_event
from mediease_api.application.context import Actor, RequestContext
from mediease_api.application.scheduling.schedules import load_clinic
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.catalogue import ACTOR_LABELS, AuditCategory, actions_in
from mediease_api.domain.audit.event import ActorType
from mediease_api.domain.shared.errors import DomainError, InvalidValue
from mediease_api.domain.shared.time import local_date
from mediease_api.ports.audit import AuditCursor, AuditEntry
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

PAGE_SIZE = 50
MAX_DAYS = 92
DEFAULT_DAYS = 7
EXPORT_MAX = 20_000
FORMER_MEMBER = "Former team member"


class AuditRangeTooLong(DomainError):
    code = "AUD_RANGE_TOO_LONG"

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Choose a shorter range: at most {MAX_DAYS} days and {EXPORT_MAX:,} entries.",
            reason=reason,
        )


@dataclass(frozen=True, slots=True)
class AuditRange:
    """Days on the clinic's calendar, both included."""

    first: date | None = None
    last: date | None = None


@dataclass(frozen=True, slots=True)
class AuditFilter:
    range: AuditRange = AuditRange()
    category: AuditCategory | None = None
    actor_user_id: UUID | None = None
    after: AuditCursor | None = None


@dataclass(frozen=True, slots=True)
class AuditPage:
    first: date
    last: date
    timezone: str
    items: Sequence[AuditEntry]
    next_cursor: AuditCursor | None


@dataclass(frozen=True, slots=True)
class AuditExport:
    first: date
    last: date
    timezone: str
    clinic_slug: str
    items: Sequence[AuditEntry]


def actor_label(entry: AuditEntry) -> str:
    """Who did it, as the owner reads it (decision 8A)."""
    if entry.actor_type is ActorType.STAFF:
        return entry.actor_name or FORMER_MEMBER
    return ACTOR_LABELS[entry.actor_type]


def _bounds(
    rng: AuditRange, *, today: date, timezone: str
) -> tuple[date, date, datetime, datetime]:
    last = rng.last or today
    first = rng.first or last - timedelta(days=DEFAULT_DAYS - 1)
    if first > last:
        raise InvalidValue("from", "must not be after the end of the range")
    if (last - first).days + 1 > MAX_DAYS:
        raise AuditRangeTooLong("days")
    zone = ZoneInfo(timezone)
    since = datetime.combine(first, time(0), tzinfo=zone).astimezone(UTC)
    until = datetime.combine(last + timedelta(days=1), time(0), tzinfo=zone).astimezone(UTC)
    return first, last, since, until


class ListAuditEvents:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, ctx: RequestContext, query: AuditFilter) -> AuditPage:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            today = local_date(self._clock.now(), clinic.timezone)
            first, last, since, until = _bounds(query.range, today=today, timezone=clinic.timezone)
            actions = actions_in(frozenset({query.category})) if query.category else None
            found = uow.tenant(ctx.clinic_id).audit_log.list(
                since=since,
                until=until,
                actions=actions,
                actor_user_id=query.actor_user_id,
                after=query.after,
                limit=PAGE_SIZE + 1,
            )
        items = found[:PAGE_SIZE]
        more = len(found) > PAGE_SIZE
        cursor = AuditCursor(items[-1].occurred_at, items[-1].id) if more else None
        return AuditPage(first, last, clinic.timezone, items, cursor)


class ExportAuditEvents:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, ctx: RequestContext, rng: AuditRange) -> AuditExport:
        with self._uow as uow:
            clinic = load_clinic(uow, ctx.clinic_id)
            now = self._clock.now()
            today = local_date(now, clinic.timezone)
            first, last, since, until = _bounds(rng, today=today, timezone=clinic.timezone)
            items = uow.tenant(ctx.clinic_id).audit_log.list(
                since=since,
                until=until,
                actions=None,
                actor_user_id=None,
                after=None,
                limit=EXPORT_MAX + 1,
            )
            if len(items) > EXPORT_MAX:
                raise AuditRangeTooLong("rows")
            record_event(
                uow,
                event_id=self._ids.new_id(),
                action=AuditAction.AUDIT_EXPORTED,
                actor=Actor.staff(ctx),
                now=now,
                clinic_id=ctx.clinic_id,
                entity_type="clinic",
                entity_id=ctx.clinic_id,
                metadata={
                    "from": first.isoformat(),
                    "to": last.isoformat(),
                    "rows": str(len(items)),
                },
            )
            uow.commit()
        logger.info("audit.exported", clinic_id=str(ctx.clinic_id), rows=len(items))
        return AuditExport(first, last, clinic.timezone, clinic.slug, items)
