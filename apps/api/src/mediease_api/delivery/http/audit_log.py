"""The owner's audit log (M6a-P8; FR-AUD-03; decision 8A).

| Endpoint | Permission |
|---|---|
| ``GET /api/v1/audit-events?from&to&category&actor_user_id&cursor`` | ``AUDIT_VIEW`` (owners) |
| ``GET /api/v1/audit-events/export?from&to`` | ``AUDIT_VIEW``; CSV, audited |

Dates are the clinic's calendar days, both included. Each entry names the person (the member's
current name and role, or "MediEase support", "System", a patient), the action in words, the record
and the metadata, which holds IDs, codes and enums only. The IP hash is never sent. Never cached.
"""

from __future__ import annotations

import base64
import csv
import io
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, jsonify, request

from mediease_api.application.audit_log.use_cases import (
    AuditFilter,
    AuditRange,
    ExportAuditEvents,
    ListAuditEvents,
    actor_label,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.scheduling import _uuid_arg
from mediease_api.delivery.http.validation import RequestValidationFailed
from mediease_api.domain.audit.catalogue import CATEGORY_LABELS, AuditCategory, describe
from mediease_api.domain.identity.permissions import Permission
from mediease_api.ports.audit import AuditCursor, AuditEntry

CSV_COLUMNS = (
    "Time",
    "Person",
    "Role",
    "Category",
    "Action",
    "Record type",
    "Record ID",
    "Patient code",
    "Details",
)
# A spreadsheet runs a cell that starts with one of these as a formula (CSV injection).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


class AuditLogUseCases(Protocol):
    def list_audit_events(self) -> ListAuditEvents: ...
    def export_audit_events(self) -> ExportAuditEvents: ...


def csv_safe(value: str) -> str:
    """A cell a spreadsheet shows as text, never runs as a formula."""
    return f"'{value}" if value.startswith(_FORMULA_START) else value


def _date_arg(name: str) -> date | None:
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise RequestValidationFailed([{"field": name, "reason": "must be YYYY-MM-DD"}]) from None


def _range() -> AuditRange:
    return AuditRange(first=_date_arg("from"), last=_date_arg("to"))


def _category() -> AuditCategory | None:
    raw = request.args.get("category")
    if not raw:
        return None
    try:
        return AuditCategory(raw)
    except ValueError:
        raise RequestValidationFailed(
            [{"field": "category", "reason": "is not a known category"}]
        ) from None


def encode_cursor(cursor: AuditCursor) -> str:
    raw = f"{cursor.occurred_at.isoformat()}|{cursor.id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _cursor() -> AuditCursor | None:
    raw = request.args.get("cursor")
    if not raw:
        return None
    try:
        text = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
        when, ident = text.split("|", 1)
        occurred = datetime.fromisoformat(when)
        if occurred.tzinfo is None:
            raise ValueError("naive")
        return AuditCursor(occurred, UUID(ident))
    except (ValueError, UnicodeDecodeError):
        raise RequestValidationFailed(
            [{"field": "cursor", "reason": "is not a cursor from this list"}]
        ) from None


def _details(metadata: Mapping[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in sorted(metadata.items()))


def entry_body(entry: AuditEntry) -> dict[str, Any]:
    info = describe(entry.action)
    return {
        "id": str(entry.id),
        "occurred_at": entry.occurred_at.isoformat(),
        "action": entry.action,
        "action_label": info.label,
        "category": info.category.value,
        "actor": {
            "type": entry.actor_type.value,
            "user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
            "label": actor_label(entry),
            "role": entry.actor_role,
        },
        "entity_type": entry.entity_type,
        "entity_id": str(entry.entity_id) if entry.entity_id else None,
        "patient_code": entry.patient_code,
        "metadata": dict(entry.metadata),
    }


def csv_rows(items: Iterable[AuditEntry], timezone: str) -> str:
    zone = ZoneInfo(timezone)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for e in items:
        info = describe(e.action)
        writer.writerow(
            [
                csv_safe(cell)
                for cell in (
                    e.occurred_at.astimezone(zone).isoformat(timespec="seconds"),
                    actor_label(e),
                    e.actor_role or "",
                    CATEGORY_LABELS[info.category],
                    info.label,
                    e.entity_type or "",
                    str(e.entity_id) if e.entity_id else "",
                    e.patient_code or "",
                    _details(e.metadata),
                )
            ]
        )
    return out.getvalue()


def create_audit_log_blueprint(use_cases: AuditLogUseCases) -> Blueprint:
    bp = Blueprint("audit_log", __name__, url_prefix="/api/v1/audit-events")

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @clinic(Permission.AUDIT_VIEW)
    def list_audit_events() -> Response:
        page = use_cases.list_audit_events().execute(
            current_context(),
            AuditFilter(
                range=_range(),
                category=_category(),
                actor_user_id=_uuid_arg("actor_user_id"),
                after=_cursor(),
            ),
        )
        return jsonify(
            {
                "from": page.first.isoformat(),
                "to": page.last.isoformat(),
                "timezone": page.timezone,
                "items": [entry_body(e) for e in page.items],
                "next_cursor": encode_cursor(page.next_cursor) if page.next_cursor else None,
                "categories": [
                    {"value": c.value, "label": label} for c, label in CATEGORY_LABELS.items()
                ],
            }
        )

    @bp.get("/export")
    @clinic(Permission.AUDIT_VIEW)
    def export_audit_events() -> Response:
        export = use_cases.export_audit_events().execute(current_context(), _range())
        name = (
            f"audit-{export.clinic_slug}-{export.first.isoformat()}-{export.last.isoformat()}.csv"
        )
        return Response(
            csv_rows(export.items, export.timezone),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    return bp
