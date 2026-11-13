"""M7e-E3 (ADR-0025; spec web-push R34, R36, R37): the push adapters, without a network.

The pywebpush adapter is given a stand-in HTTP session, so the test sees the exact request a push
service would get, decrypts it as the browser would, and answers with each status.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import http_ece
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from mediease_api.adapters.push.console import ConsolePushAdapter
from mediease_api.adapters.push.webpush import PyWebPushAdapter, failure_for
from mediease_api.ports.push import PushFailed, PushFailure, PushTarget

ENDPOINT = "https://fcm.googleapis.com/fcm/send/device-1:APA91b-test"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _point(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


def vapid_pair() -> tuple[str, str]:
    """A synthetic VAPID pair as the settings hold it: raw private key, uncompressed public."""
    key = ec.generate_private_key(ec.SECP256R1())
    return _b64(key.private_numbers().private_value.to_bytes(32, "big")), _b64(_point(key))


class Browser:
    """The receiving side: its key pair and auth secret, and a way to read what was sent."""

    def __init__(self) -> None:
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.target = PushTarget(ENDPOINT, _b64(_point(self.key)), _b64(self.auth))

    def read(self, body: bytes) -> str:
        plain: bytes = http_ece.decrypt(
            body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"
        )
        return plain.decode("utf-8")


class Response:
    def __init__(self, status: int) -> None:
        self.status_code = status
        self.reason = "test"
        self.text = ""
        self.headers: dict[str, str] = {}


class Session:
    """Stands in for ``requests.Session``: records the call, answers ``status`` or raises."""

    def __init__(self, status: int = 201, raises: Exception | None = None) -> None:
        self.status = status
        self.raises = raises
        self.calls: list[dict[str, Any]] = []
        self.max_redirects = 30

    def post(self, url: str, **kwargs: Any) -> Response:
        self.calls.append({"url": url, **kwargs})
        if self.raises is not None:
            raise self.raises
        return Response(self.status)


def _adapter(session: Session) -> PyWebPushAdapter:
    private, public = vapid_pair()
    return PyWebPushAdapter(
        private_key=private,
        public_key=public,
        subject="mailto:push@mediease.example",
        session=session,  # type: ignore[arg-type]
    )


def test_r36_an_accepted_push_is_encrypted_for_the_browser_and_signed() -> None:
    session, browser = Session(201), Browser()
    adapter = _adapter(session)
    assert session.max_redirects == 0  # R12: never followed elsewhere
    adapter.send(browser.target, json.dumps({"title": "Hello"}), ttl=3600)
    [call] = session.calls
    assert call["url"] == ENDPOINT
    assert call["timeout"] == 10.0
    headers = call["headers"]
    assert headers["TTL"] == "3600" and headers["Urgency"] == "normal"
    assert headers["content-encoding"] == "aes128gcm"
    assert headers["Authorization"].startswith("vapid t=")
    assert b"Hello" not in call["data"]  # the push service cannot read it
    assert json.loads(browser.read(call["data"])) == {"title": "Hello"}


@pytest.mark.parametrize(
    ("status", "failure"),
    [
        (404, PushFailure.GONE),
        (410, PushFailure.GONE),
        (429, PushFailure.RATE_LIMITED),
        (500, PushFailure.UNAVAILABLE),
        (503, PushFailure.UNAVAILABLE),
        (400, PushFailure.REFUSED),
        (403, PushFailure.REFUSED),
        (413, PushFailure.REFUSED),
    ],
)
def test_r34_r36_each_answer_is_mapped(status: int, failure: PushFailure) -> None:
    with pytest.raises(PushFailed) as raised:
        _adapter(Session(status)).send(Browser().target, "{}", ttl=60)
    assert (raised.value.failure, raised.value.status) == (failure, status)
    assert raised.value.failure.retryable is (
        failure in (PushFailure.RATE_LIMITED, PushFailure.UNAVAILABLE)
    )


@pytest.mark.parametrize(
    ("error", "failure"),
    [
        (requests.ConnectionError("down"), PushFailure.UNAVAILABLE),
        (requests.Timeout("slow"), PushFailure.UNAVAILABLE),
        (requests.TooManyRedirects("moved"), PushFailure.REFUSED),
    ],
)
def test_r36_no_answer_is_retried_and_a_redirect_is_refused(
    error: Exception, failure: PushFailure
) -> None:
    with pytest.raises(PushFailed) as raised:
        _adapter(Session(raises=error)).send(Browser().target, "{}", ttl=60)
    assert raised.value.failure is failure


def test_a_private_key_from_another_pair_stops_start_up() -> None:
    private, _ = vapid_pair()
    _, other_public = vapid_pair()
    with pytest.raises(ValueError, match="pair"):
        PyWebPushAdapter(private_key=private, public_key=other_public, subject="mailto:a@b.example")


def test_failure_for_unknown_answers_is_refused() -> None:
    assert failure_for(None) is PushFailure.REFUSED
    assert failure_for(302) is PushFailure.REFUSED


def test_m7e_e5_a_key_that_cannot_be_encrypted_for_is_refused_not_retried() -> None:
    """Found on the developer's device test: such a key raised ValueError and the job retried."""
    session = Session(201)
    bad = PushTarget(ENDPOINT, _b64(b"\x04" + bytes(range(64))), _b64(bytes(16)))
    with pytest.raises(PushFailed) as raised:
        _adapter(session).send(bad, "{}", ttl=60)
    assert raised.value.failure is PushFailure.REFUSED and not raised.value.failure.retryable
    assert session.calls == []


def test_r37_the_console_logs_no_endpoint_or_message(json_logs: Any) -> None:
    console = ConsolePushAdapter()
    target = Browser().target
    console.send(target, '{"title":"secret-words"}', ttl=60)
    assert console.sent == [(target, '{"title":"secret-words"}', 60)]
    logs = json.dumps(json_logs())
    assert "fcm.googleapis.com" not in logs and "secret-words" not in logs
    assert "fcm" not in repr(target)


def test_build_push_console_locally_and_refused_in_production(
    set_env: Any, valid_env: dict[str, str]
) -> None:
    from mediease_api.bootstrap import build_push
    from mediease_api.config.settings import AppSettings

    set_env({**valid_env, "APP_ENV": "test"})
    assert isinstance(build_push(AppSettings()), ConsolePushAdapter)  # type: ignore[call-arg]
    private, public = vapid_pair()
    set_env(
        {
            "PUSH_PROVIDER": "webpush",
            "VAPID_PRIVATE_KEY": private,
            "VAPID_PUBLIC_KEY": public,
            "VAPID_SUBJECT": "https://mediease.example/contact",
        }
    )
    assert isinstance(build_push(AppSettings()), PyWebPushAdapter)  # type: ignore[call-arg]
    set_env({"PUSH_PROVIDER": "console", "APP_ENV": "production", "COOKIE_SECURE": "true"})
    with pytest.raises(ValueError, match="PUSH_PROVIDER=console"):
        build_push(AppSettings())  # type: ignore[call-arg]
