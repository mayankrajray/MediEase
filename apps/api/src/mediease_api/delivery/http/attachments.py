"""Reports attached to visits (M6d-P6; FR-VIS-04; spec visit-attachments; B8, D7).

Under ``/api/v1/visits/{visit_id}/attachments``:

| Endpoint | Permission |
|---|---|
| ``POST ""`` | ``ATTACHMENTS_ADD`` (every role) |
| ``GET ""`` | ``CLINICAL_VIEW`` |
| ``GET /{attachment_id}/file`` | ``CLINICAL_VIEW``, audited |
| ``DELETE /{attachment_id}`` | ``ATTACHMENTS_ADD`` (the uploader, within 24 hours) |
| ``PUT /{attachment_id}/share`` | ``CLINICAL_WRITE`` (the visit's doctor) |

The upload is ``multipart/form-data`` with one part ``file``; the request is capped just above
10 MB before it is parsed (413). A file is served ``inline`` with ``nosniff`` and a sandbox CSP, so
a browser never runs anything in it, and never cached.
"""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import quote
from uuid import UUID

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, ConfigDict
from werkzeug.exceptions import UnsupportedMediaType

from mediease_api.application.visits.attachments import (
    AddAttachment,
    AttachmentFile,
    AttachmentItem,
    DeleteAttachment,
    ListAttachments,
    OpenAttachment,
    PortalAttachment,
    ShareAttachment,
)
from mediease_api.delivery.http.access import clinic, current_context
from mediease_api.delivery.http.validation import parse_json
from mediease_api.domain.identity.permissions import Permission
from mediease_api.domain.visits.attachment import MAX_ATTACHMENT_BYTES, VisitAttachment

# R2: the file plus the multipart framing and a name; anything larger is refused unread.
MAX_UPLOAD_REQUEST_BYTES = MAX_ATTACHMENT_BYTES + 64 * 1024


class AttachmentUseCases(Protocol):
    def add_attachment(self) -> AddAttachment: ...
    def list_attachments(self) -> ListAttachments: ...
    def open_attachment(self) -> OpenAttachment: ...
    def delete_attachment(self) -> DeleteAttachment: ...
    def share_attachment(self) -> ShareAttachment: ...


class ShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared: bool


def _attachment_fields(a: VisitAttachment) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "visit_id": str(a.visit_id),
        "filename": a.filename,
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
        "uploaded_at": a.uploaded_at.isoformat(),
        "shared_with_patient": a.is_shared,
        "shared_at": a.shared_at.isoformat() if a.shared_at else None,
    }


def attachment_body(item: AttachmentItem) -> dict[str, Any]:
    a = item.attachment
    return {
        **_attachment_fields(a),
        "uploaded_by_user_id": str(a.uploaded_by),
        "can_delete": item.can_delete,
        "deletable_until": a.locked_at.isoformat(),
    }


def portal_attachment_body(p: PortalAttachment) -> dict[str, Any]:
    a = p.attachment
    return {
        "id": str(a.id),
        "clinic_id": str(p.clinic_id),
        "clinic_name": p.clinic_name,
        "filename": a.filename,
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
        "visit_date": p.visit_started_at.isoformat(),
        "shared_at": a.shared_at.isoformat() if a.shared_at else None,
    }


def _ascii(name: str) -> str:
    return "".join(c if 32 <= ord(c) < 127 and c not in '"\\;' else "_" for c in name)


def file_response(file: AttachmentFile) -> Response:
    """R7: inline, its real type, never sniffed or run, never cached."""
    response = Response(file.data, mimetype=file.content_type)
    response.headers["Content-Disposition"] = (
        f"inline; filename=\"{_ascii(file.filename)}\"; filename*=UTF-8''{quote(file.filename)}"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response.headers["Cache-Control"] = "private, no-store"
    return response


def create_attachments_blueprint(use_cases: AttachmentUseCases) -> Blueprint:
    bp = Blueprint("attachments", __name__, url_prefix="/api/v1/visits/<uuid:visit_id>/attachments")
    one = "/<uuid:attachment_id>"

    @bp.after_request
    def _no_store(response: Response) -> Response:
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @bp.post("")
    @clinic(Permission.ATTACHMENTS_ADD)
    def add_attachment(visit_id: UUID) -> tuple[Response, int]:
        request.max_content_length = MAX_UPLOAD_REQUEST_BYTES
        if request.mimetype != "multipart/form-data":
            raise UnsupportedMediaType("Send the report as multipart/form-data.")
        part = request.files.get("file")
        data = part.stream.read(MAX_ATTACHMENT_BYTES + 1) if part is not None else None
        item = use_cases.add_attachment().execute(
            current_context(),
            visit_id=visit_id,
            data=data,
            filename=part.filename if part is not None else None,
        )
        return jsonify(attachment_body(item)), 201

    @bp.get("")
    @clinic(Permission.CLINICAL_VIEW)
    def list_attachments(visit_id: UUID) -> Response:
        items = use_cases.list_attachments().execute(current_context(), visit_id=visit_id)
        return jsonify({"items": [attachment_body(i) for i in items]})

    @bp.get(f"{one}/file")
    @clinic(Permission.CLINICAL_VIEW)
    def attachment_file(visit_id: UUID, attachment_id: UUID) -> Response:
        file = use_cases.open_attachment().execute(
            current_context(), visit_id=visit_id, attachment_id=attachment_id
        )
        return file_response(file)

    @bp.delete(one)
    @clinic(Permission.ATTACHMENTS_ADD)
    def delete_attachment(visit_id: UUID, attachment_id: UUID) -> tuple[str, int]:
        use_cases.delete_attachment().execute(
            current_context(), visit_id=visit_id, attachment_id=attachment_id
        )
        return "", 204

    @bp.put(f"{one}/share")
    @clinic(Permission.CLINICAL_WRITE)
    def share_attachment(visit_id: UUID, attachment_id: UUID) -> Response:
        body = parse_json(ShareIn)
        item = use_cases.share_attachment().execute(
            current_context(), visit_id=visit_id, attachment_id=attachment_id, shared=body.shared
        )
        return jsonify(attachment_body(item))

    return bp
