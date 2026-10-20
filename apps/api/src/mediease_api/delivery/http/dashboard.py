"""The role dashboards (M6-P1; decisions 5A, 6A).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/dashboard/today`` | ``CLINIC_VIEW`` (the 7-day strip: ``USAGE_METRICS_VIEW``) |

Every clinic role holds ``CLINIC_VIEW``. The body is counts, codes, first names, times and
statuses only, never clinical text. Like the queue, the 200 carries a strong ETag and an
unchanged answer is a bodiless 304 (R12), so the screen can poll every 5 seconds cheaply.
"""

from __future__ import annotations

from typing import Any, Protocol

from flask import Blueprint, Response

from mediease_api.application.dashboard.today import GetToday, TodaySession, TodayView
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.etag import conditional_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.ports.dashboard import DayTotals, NextPatient, StatusCounts


class DashboardUseCases(Protocol):
    def get_today(self) -> GetToday: ...


def counts_body(c: StatusCounts) -> dict[str, int]:
    return {
        "total": c.total,
        "not_arrived": c.not_arrived,
        "waiting": c.waiting,
        "in_consultation": c.in_consultation,
        "completed": c.completed,
        "no_show": c.no_show,
    }


def _session_body(item: TodaySession) -> dict[str, Any]:
    s = item.session
    return {
        "id": str(s.id),
        "doctor_id": str(s.doctor_id),
        "doctor_name": item.doctor_name,
        "starts_at": s.starts_at.isoformat(),
        "ends_at": s.ends_at.isoformat(),
        "status": s.status.value,
        "mode": s.mode.value,
        "capacity": s.capacity,
        "counts": counts_body(item.counts),
    }


def _next_body(n: NextPatient) -> dict[str, Any]:
    return {
        "appointment_id": str(n.appointment_id),
        "session_id": str(n.session_id),
        "doctor_id": str(n.doctor_id),
        "status": n.status,
        "token_number": n.token_number,
        "slot_start": n.slot_start.isoformat() if n.slot_start else None,
        "patient_code": n.patient_code,
        "patient_first_name": n.patient_first_name,
    }


def _day_body(d: DayTotals) -> dict[str, Any]:
    return {
        "on_date": d.on_date.isoformat(),
        "appointments": d.appointments,
        "completed": d.completed,
        "no_show": d.no_show,
        "messages_sent": d.messages_sent,
    }


def today_body(view: TodayView) -> dict[str, Any]:
    return {
        "on_date": view.on_date.isoformat(),
        "scope": view.scope.value,
        "doctor_id": str(view.doctor_id) if view.doctor_id else None,
        "counts": counts_body(view.counts),
        "sessions": [_session_body(s) for s in view.sessions],
        "next_patients": [_next_body(n) for n in view.next_patients],
        "follow_ups_pending": view.follow_ups_pending,
        "messages_failed": view.messages_failed,
        "week": [_day_body(d) for d in view.week] if view.week is not None else None,
    }


def create_dashboard_blueprint(use_cases: DashboardUseCases) -> Blueprint:
    bp = Blueprint("dashboard", __name__, url_prefix="/api/v1")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("/dashboard/today")
    @clinic(Permission.CLINIC_VIEW)
    def get_today() -> Response:
        view = use_cases.get_today().execute(current_context())
        return conditional_json(today_body(view))

    return bp
