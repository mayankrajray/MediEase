"""A session running now, for tests of the queue (M3-P3).

The app runs on the system clock and the queue only moves on the session's day (D19), so these
tests cannot use a fixed weekly block: at 19:00 a 10:00-13:00 session has already ended. Instead
the doctor gets an extra session that started a few minutes ago and runs for an hour. Use it for
a doctor without weekly blocks, so the extra cannot overlap one (R15).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from flask.testing import FlaskClient

KOLKATA = ZoneInfo("Asia/Kolkata")


def _headers(client: FlaskClient) -> dict[str, str]:
    csrf = client.get_cookie("me_csrf", path="/")
    assert csrf is not None
    return {"X-CSRF-Token": csrf.value}


def running_session(
    owner: FlaskClient, doctor_id: object, *, capacity: int = 12, slot: int | None = None
) -> dict[str, Any]:
    """Add an extra session from about five minutes ago for an hour; return it from the list."""
    now = datetime.now(KOLKATA)
    start = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % 5 + 5)
    if start.date() != now.date():  # just after midnight: start at 00:00 instead
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    extra: dict[str, Any] = {
        "kind": "EXTRA",
        "on_date": now.date().isoformat(),
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
        "capacity": capacity,
    }
    if slot is not None:
        extra["slot_minutes"] = slot
    added = owner.post(
        f"/api/v1/clinic/doctors/{doctor_id}/schedule-exceptions",
        json=extra,
        headers=_headers(owner),
    )
    assert added.status_code == 201, added.get_json()
    listed = owner.get(f"/api/v1/sessions?date={now.date().isoformat()}&doctor_id={doctor_id}")
    starts = start.astimezone(ZoneInfo("UTC")).isoformat()
    return next(s for s in listed.get_json()["items"] if s["starts_at"] == starts)
