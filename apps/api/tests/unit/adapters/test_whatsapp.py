"""The WhatsApp Cloud API adapter, signature check and webhook parsing (M5-P3; spec R7, R13)."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from collections.abc import Iterator, Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from mediease_api.adapters.messaging.catalog import YamlTemplateCatalog
from mediease_api.adapters.messaging.whatsapp_cloud import (
    HttpResult,
    RequestNeverSent,
    WhatsAppCloudAdapter,
    request_body,
    urllib_transport,
)
from mediease_api.adapters.messaging.whatsapp_errors import map_meta_error
from mediease_api.adapters.messaging.whatsapp_webhook import (
    HmacWebhookVerifier,
    WhatsAppWebhookParser,
)
from mediease_api.domain.messaging.errors import (
    MSG_PROVIDER_AUTH,
    MSG_PROVIDER_RATE_LIMIT,
    MSG_PROVIDER_REJECTED,
    MSG_PROVIDER_UNAVAILABLE,
    MSG_RECIPIENT_INVALID,
    MSG_TEMPLATE_NOT_FOUND,
    MSG_TEMPLATE_PARAMS,
    ProviderOutcomeUnknown,
    ProviderRefused,
)
from mediease_api.domain.messaging.message import Channel, MessageStatus
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.messaging import OutboundTemplateMessage
from tests.builders import new_id
from tests.conftest import LogReader

PHONE = PhoneNumber.parse("9000000001")
CATALOG = YamlTemplateCatalog.from_package()
MESSAGE_ID = new_id()


def _msg(
    key: str = "booking_confirmed", language: Language = Language.HI
) -> OutboundTemplateMessage:
    values = {
        "booking_confirmed": {
            "clinic_name": "Sample Clinic",
            "doctor_name": "Dr. Sample",
            "date_time_or_token": "20/10/2026, 10:30",
        },
        "opt_out_confirmed": {"clinic_name": "Sample Clinic"},
    }[key]
    return OutboundTemplateMessage(
        idempotency_key=f"{key}:1",
        to=PHONE,
        template=CATALOG.get(key),
        language=language,
        variables=values,
        message_id=MESSAGE_ID,
    )


class FakeTransport:
    def __init__(self, result: HttpResult | BaseException) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any], Mapping[str, str], float]] = []

    def __call__(
        self, url: str, body: bytes, headers: Mapping[str, str], timeout: float
    ) -> HttpResult:
        self.calls.append((url, json.loads(body), headers, timeout))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def _adapter(transport: FakeTransport) -> WhatsAppCloudAdapter:
    return WhatsAppCloudAdapter(
        phone_number_id="123456789",
        access_token="test-token",
        api_version="v26.0",
        transport=transport,
    )


def _error(status: int, code: int) -> HttpResult:
    return HttpResult(status, json.dumps({"error": {"code": code, "message": "x"}}).encode())


# --- The send call (R7) -------------------------------------------------------------------------


def test_r7_a_template_is_sent_with_its_parameters_in_order_and_our_id() -> None:
    transport = FakeTransport(HttpResult(200, b'{"messages": [{"id": "wamid.ABC"}]}'))
    adapter = _adapter(transport)
    assert adapter.send_template(_msg()).provider_message_id == "wamid.ABC"
    assert (adapter.channel, adapter.provider) == (Channel.WHATSAPP, "whatsapp_cloud")
    [(url, body, headers, timeout)] = transport.calls
    assert url == "https://graph.facebook.com/v26.0/123456789/messages"
    assert headers["Authorization"] == "Bearer test-token" and timeout == 10.0
    assert body["to"] == "919000000001" and body["type"] == "template"
    assert body["biz_opaque_callback_data"] == str(MESSAGE_ID)
    template = body["template"]
    assert (template["name"], template["language"]) == ("booking_confirmed_v1", {"code": "hi"})
    assert [p["text"] for p in template["components"][0]["parameters"]] == [
        "Sample Clinic",
        "Dr. Sample",
        "20/10/2026, 10:30",
    ]


def test_a_service_reply_is_plain_text_inside_the_window() -> None:
    body = request_body(_msg("opt_out_confirmed", Language.EN))
    assert body["type"] == "text"
    assert body["text"] == {"body": "You will no longer receive messages from Sample Clinic."}


@pytest.mark.parametrize(
    ("result", "code", "retryable"),
    [
        (_error(400, 130429), MSG_PROVIDER_RATE_LIMIT, True),
        (_error(400, 131056), MSG_PROVIDER_RATE_LIMIT, True),
        (_error(500, 131000), MSG_PROVIDER_UNAVAILABLE, True),
        (HttpResult(503, b"<html>busy</html>"), MSG_PROVIDER_UNAVAILABLE, True),
        (_error(404, 132001), MSG_TEMPLATE_NOT_FOUND, False),
        (_error(400, 132000), MSG_TEMPLATE_PARAMS, False),
        (_error(400, 131026), MSG_RECIPIENT_INVALID, False),
        (_error(401, 190), MSG_PROVIDER_AUTH, False),
        (HttpResult(401, b""), MSG_PROVIDER_AUTH, False),
        (_error(400, 999999), MSG_PROVIDER_REJECTED, False),
    ],
)
def test_r7_meta_errors_are_refusals_mapped_to_our_codes(
    result: HttpResult, code: str, retryable: bool, json_logs: LogReader
) -> None:
    with pytest.raises(ProviderRefused) as refused:
        _adapter(FakeTransport(result)).send_template(_msg())
    assert (refused.value.code, refused.value.retryable) == (code, retryable)
    assert "Sample Clinic" not in json.dumps(json_logs())  # Meta's text can echo parameters


@pytest.mark.parametrize(
    "result",
    [
        TimeoutError("read timed out"),
        OSError("connection reset"),
        HttpResult(200, b"not json"),
        HttpResult(200, b'{"messages": []}'),
    ],
)
def test_decision_4a_a_lost_or_unreadable_answer_is_an_unknown_outcome(
    result: HttpResult | BaseException,
) -> None:
    with pytest.raises(ProviderOutcomeUnknown):
        _adapter(FakeTransport(result)).send_template(_msg())


def test_a_connection_that_never_opened_is_a_retryable_refusal() -> None:
    with pytest.raises(ProviderRefused) as refused:
        _adapter(FakeTransport(RequestNeverSent("ConnectionRefusedError"))).send_template(_msg())
    assert refused.value.code == MSG_PROVIDER_UNAVAILABLE


def test_unknown_or_malformed_meta_codes_are_permanent_refusals() -> None:
    assert map_meta_error(None) == MSG_PROVIDER_REJECTED
    assert map_meta_error("130429") == MSG_PROVIDER_RATE_LIMIT


# --- The real transport against a local server --------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        if self.path.endswith("/slow/messages"):
            threading.Event().wait(1.0)
        status = 200 if body["to"] == "919000000001" else 400
        payload = (
            {"messages": [{"id": "wamid.LOCAL"}]} if status == 200 else {"error": {"code": 131026}}
        )
        data = json.dumps(payload).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_the_urllib_transport_reads_success_errors_and_times_out(server: str) -> None:
    def adapter(phone_id: str, timeout: float = 10.0) -> WhatsAppCloudAdapter:
        return WhatsAppCloudAdapter(
            phone_number_id=phone_id,
            access_token="t",
            api_version="v26.0",
            graph_url=server,
            transport=urllib_transport,
            timeout=timeout,
        )

    assert adapter("1").send_template(_msg()).provider_message_id == "wamid.LOCAL"
    other = OutboundTemplateMessage(
        idempotency_key="k",
        to=PhoneNumber.parse("9000000002"),
        template=CATALOG.get("opt_out_confirmed"),
        language=Language.EN,
        variables={"clinic_name": "Sample Clinic"},
    )
    with pytest.raises(ProviderRefused) as refused:
        adapter("1").send_template(other)
    assert refused.value.code == MSG_RECIPIENT_INVALID
    with pytest.raises(ProviderOutcomeUnknown):
        adapter("slow", timeout=0.2).send_template(_msg())


def test_a_refused_connection_never_reached_meta() -> None:
    with pytest.raises(RequestNeverSent):
        urllib_transport("http://127.0.0.1:9/x", b"{}", {}, 1.0)


# --- Signature (R13, AC6) -----------------------------------------------------------------------


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_r13_only_a_body_signed_with_our_secret_verifies() -> None:
    body = b'{"object":"whatsapp_business_account"}'
    verifier = HmacWebhookVerifier("app-secret-for-tests")
    assert verifier.verify(body, _sign("app-secret-for-tests", body))
    assert verifier.verify(
        body, _sign("app-secret-for-tests", body).upper().replace("SHA256=", "sha256=")
    )
    assert not verifier.verify(body + b" ", _sign("app-secret-for-tests", body))  # re-serialised
    assert not verifier.verify(body, _sign("another-secret", body))
    assert not verifier.verify(body, hmac.new(b"x", body, hashlib.sha256).hexdigest())  # no prefix
    assert not verifier.verify(body, None)
    assert not HmacWebhookVerifier("").verify(body, _sign("", body))  # no secret, no trust


# --- Redaction and parsing (decision 3A) --------------------------------------------------------

DOCUMENT: dict[str, Any] = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WABA-1",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": "15550001111", "phone_number_id": "1"},
                        "contacts": [
                            {"profile": {"name": "Sample Person"}, "wa_id": "919000000001"}
                        ],
                        "messages": [
                            {
                                "from": "919000000001",
                                "id": "wamid.IN",
                                "timestamp": "1792300000",
                                "type": "text",
                                "text": {"body": "my fever is worse"},
                            }
                        ],
                        "statuses": [
                            {
                                "id": "wamid.1",
                                "status": "delivered",
                                "timestamp": "1792300000",
                                "recipient_id": "919000000001",
                                "biz_opaque_callback_data": str(MESSAGE_ID),
                                "pricing": {"category": "utility", "billable": True},
                                "conversation": {"id": "c1", "origin": {"type": "utility"}},
                            },
                            {
                                "id": "wamid.2",
                                "status": "failed",
                                "timestamp": "1792300001",
                                "recipient_id": "919000000002",
                                "errors": [{"code": 131026, "title": "Message undeliverable"}],
                            },
                            {"id": "wamid.3", "status": "deleted", "timestamp": "1792300002"},
                            {"id": "wamid.4", "status": "read", "timestamp": "soon"},
                        ],
                    },
                }
            ],
        }
    ],
}


def test_decision_3a_the_stored_payload_has_no_text_names_or_numbers() -> None:
    parser = WhatsAppWebhookParser()
    stored = json.dumps(parser.redact(DOCUMENT))
    for secret in ("my fever", "Sample Person", "919000000001", "919000000002", "15550001111"):
        assert secret not in stored
    assert "wamid.IN" in stored and str(MESSAGE_ID) in stored
    assert parser.event_key(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_r13_statuses_are_parsed_with_our_id_codes_and_category() -> None:
    parser = WhatsAppWebhookParser()
    delivered, failed = parser.statuses(parser.redact(DOCUMENT))
    assert (delivered.provider_message_id, delivered.message_id, delivered.status) == (
        "wamid.1",
        MESSAGE_ID,
        MessageStatus.DELIVERED,
    )
    assert delivered.pricing_category == "utility" and delivered.error_code is None
    assert delivered.at.timestamp() == 1792300000
    assert (failed.status, failed.error_code, failed.message_id) == (
        MessageStatus.FAILED,
        MSG_RECIPIENT_INVALID,
        None,
    )
    assert parser.statuses({"entry": "nonsense"}) == []
