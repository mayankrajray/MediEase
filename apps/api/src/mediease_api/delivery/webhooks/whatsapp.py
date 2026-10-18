"""WhatsApp Cloud API webhooks (M5-P3; FR-MSG-03; spec R12, R13; AC6; decisions 2A, 5A).

| Endpoint | Access |
|---|---|
| ``GET /webhooks/whatsapp`` | public; Meta's subscription challenge with our verify token |
| ``POST /webhooks/whatsapp`` | public; ``X-Hub-Signature-256`` over the raw body |

The body is read raw (1 MB at most, else 413) and handed to the use case, which checks the
signature before parsing it. A valid body is stored and enqueued and answered ``200`` at once;
a bad signature is ``401 WH_SIGNATURE_INVALID`` and nothing is stored. No session, no cookie, no
CSRF (outside ``/api/``).
"""

from __future__ import annotations

from typing import Protocol

from flask import Blueprint, Response, jsonify, request

from mediease_api.application.messaging.webhooks import ReceiveWebhook, VerifyWebhookSubscription
from mediease_api.delivery.http.access import public
from mediease_api.delivery.http.request_info import request_info

MAX_BODY_BYTES = 1024 * 1024
SIGNATURE_HEADER = "X-Hub-Signature-256"


class WebhookUseCases(Protocol):
    def verify_whatsapp_subscription(self) -> VerifyWebhookSubscription: ...
    def receive_whatsapp_webhook(self) -> ReceiveWebhook: ...


def create_whatsapp_webhook_blueprint(use_cases: WebhookUseCases) -> Blueprint:
    bp = Blueprint("whatsapp_webhook", __name__, url_prefix="/webhooks/whatsapp")

    @bp.after_request
    def _private(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.get("")
    @public
    def verify_whatsapp_subscription() -> Response:
        challenge = use_cases.verify_whatsapp_subscription().execute(
            mode=request.args.get("hub.mode"),
            token=request.args.get("hub.verify_token"),
            challenge=request.args.get("hub.challenge"),
        )
        return Response(challenge, status=200, mimetype="text/plain")

    @bp.post("")
    @public
    def receive_whatsapp_webhook() -> Response:
        request.max_content_length = MAX_BODY_BYTES
        body = request.get_data(cache=False)
        use_cases.receive_whatsapp_webhook().execute(
            body, request.headers.get(SIGNATURE_HEADER), request_info()
        )
        return jsonify({"status": "received"})

    return bp
