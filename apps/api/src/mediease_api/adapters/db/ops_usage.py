"""The ops clinic usage report (M9-P4; FR-OPS-03): a reviewed cross-clinic read of counts only.

Weeks are Monday to Sunday in each clinic's own time zone. Pilot scale (a handful of clinics,
thousands of rows): each query is one grouped scan; nothing here returns a row about a person.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from mediease_api.domain.messaging.errors import MSG_CHANNEL_DISABLED
from mediease_api.ports.ops import ClinicUsageFacts, UsageMetric

_CLINICS = text(
    """
    SELECT c.id, c.name, c.slug, c.status, c.timezone, c.created_at,
           count(m.id) FILTER (WHERE m.role = 'OWNER') AS owners,
           (SELECT count(*) FROM doctors d WHERE d.clinic_id = c.id AND d.is_active) AS doctors,
           count(m.id) FILTER (WHERE m.role = 'FRONT_DESK') AS front_desk,
           count(DISTINCT m.user_id) AS members,
           max(u.last_login_at) AS last_sign_in_at
    FROM clinics c
    LEFT JOIN clinic_memberships m ON m.clinic_id = c.id AND m.status = 'ACTIVE'
    LEFT JOIN users u ON u.id = m.user_id
    GROUP BY c.id
    ORDER BY c.created_at DESC, c.id
    """
)

# A member is active when they signed in, or did something audited in this clinic, since :since.
_ACTIVE_USERS = text(
    """
    SELECT m.clinic_id, count(DISTINCT m.user_id) AS active
    FROM clinic_memberships m
    JOIN users u ON u.id = m.user_id
    WHERE m.status = 'ACTIVE'
      AND (u.last_login_at >= :since
           OR EXISTS (SELECT 1 FROM audit_events e
                      WHERE e.clinic_id = m.clinic_id AND e.actor_user_id = m.user_id
                        AND e.occurred_at >= :since))
    GROUP BY m.clinic_id
    """
)

_LAST_EVENT = text(
    """
    SELECT clinic_id, max(occurred_at) AS last_event_at
    FROM audit_events WHERE clinic_id IS NOT NULL
    GROUP BY clinic_id
    """
)

# Each record at the time it was made, read as a clinic-local week (Monday).
_RECORDS = text(
    """
    SELECT r.clinic_id, r.metric,
           date_trunc('week', r.at AT TIME ZONE c.timezone)::date AS week_start,
           count(*) AS n, max(r.at) AS last_at
    FROM (
        SELECT clinic_id, 'patients' AS metric, created_at AS at FROM patients
        UNION ALL
        SELECT clinic_id, 'appointments', created_at FROM appointments
         WHERE status <> 'CANCELLED'
        UNION ALL
        SELECT clinic_id, 'visits', started_at FROM visits
        UNION ALL
        SELECT clinic_id, 'prescriptions', issued_at FROM prescriptions
         WHERE issued_at IS NOT NULL
        UNION ALL
        SELECT clinic_id, 'bills', issued_at FROM bills
         WHERE kind = 'BILL' AND issued_at IS NOT NULL
    ) r
    JOIN clinics c ON c.id = r.clinic_id
    GROUP BY r.clinic_id, r.metric, week_start
    """
)

_MESSAGES = text(
    """
    SELECT clinic_id,
           count(*) FILTER (WHERE error_code IS DISTINCT FROM :disabled) AS failed,
           count(*) FILTER (WHERE error_code = :disabled) AS not_sent
    FROM messages
    WHERE status = 'FAILED' AND failed_at >= :since
    GROUP BY clinic_id
    """
)

_JOBS = text(
    """
    SELECT clinic_id, count(*) AS failed
    FROM jobs
    WHERE state = 'dead' AND clinic_id IS NOT NULL AND finished_at >= :since
    GROUP BY clinic_id
    """
)


class SqlAlchemyClinicUsageReport:
    """``ClinicUsageReport``: reached only from the ops console (``@ops``)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def facts(self, *, since: datetime) -> Sequence[ClinicUsageFacts]:
        run = self._session.execute
        active = {r.clinic_id: int(r.active) for r in run(_ACTIVE_USERS, {"since": since})}
        last_event = {r.clinic_id: r.last_event_at for r in run(_LAST_EVENT)}
        counts: dict[UUID, dict[tuple[UsageMetric, date], int]] = defaultdict(dict)
        last_record: dict[UUID, datetime] = {}
        for r in run(_RECORDS):
            counts[r.clinic_id][(UsageMetric(r.metric), r.week_start)] = int(r.n)
            if r.clinic_id not in last_record or r.last_at > last_record[r.clinic_id]:
                last_record[r.clinic_id] = r.last_at
        messages = {
            r.clinic_id: (int(r.failed), int(r.not_sent))
            for r in run(_MESSAGES, {"since": since, "disabled": MSG_CHANNEL_DISABLED})
        }
        jobs = {r.clinic_id: int(r.failed) for r in run(_JOBS, {"since": since})}
        facts = []
        for c in run(_CLINICS):
            moments = [
                m for m in (c.last_sign_in_at, last_event.get(c.id), last_record.get(c.id)) if m
            ]
            failed, not_sent = messages.get(c.id, (0, 0))
            facts.append(
                ClinicUsageFacts(
                    clinic_id=c.id,
                    name=c.name,
                    slug=c.slug,
                    status=c.status,
                    timezone=c.timezone,
                    created_at=c.created_at,
                    owners=int(c.owners),
                    doctors=int(c.doctors),
                    front_desk=int(c.front_desk),
                    members=int(c.members),
                    active_users_7d=active.get(c.id, 0),
                    last_active_at=max(moments) if moments else None,
                    counts=counts.get(c.id, {}),
                    failed_messages_7d=failed,
                    not_sent_7d=not_sent,
                    failed_jobs_7d=jobs.get(c.id, 0),
                )
            )
        return facts
