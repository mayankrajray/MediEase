"""Web push through the browsers' push services with ``pywebpush`` (M7e-E3, ADR-0025).

Each message is encrypted for the one browser (RFC 8291, aes128gcm) and carries a VAPID header
signed with our private key (RFC 8292), so the push service knows the sender and cannot read the
message. The answer is mapped to a ``PushFailure``: 404 and 410 mean the browser unsubscribed,
429 and 5xx (or no answer in time) are worth retrying, anything else is not.

Redirects are refused (a push service answers, it does not send us elsewhere), so the request can
only ever go to the allow-listed host the endpoint names (spec web-push R12). Nothing about the
endpoint or the message is logged.
"""

from __future__ import annotations

import base64

import requests
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from mediease_api.ports.push import PushFailed, PushFailure, PushTarget

TIMEOUT_SECONDS = 10.0


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def failure_for(status: int | None) -> PushFailure:
    if status in (404, 410):
        return PushFailure.GONE
    if status == 429:
        return PushFailure.RATE_LIMITED
    if status is not None and 500 <= status <= 599:
        return PushFailure.UNAVAILABLE
    return PushFailure.REFUSED


class PyWebPushAdapter:
    provider = "webpush"

    def __init__(
        self,
        *,
        private_key: str,
        public_key: str,
        subject: str,
        timeout_seconds: float = TIMEOUT_SECONDS,
        session: requests.Session | None = None,
    ) -> None:
        self._vapid = Vapid.from_raw(private_key.encode("ascii"))
        derived = self._vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        if _b64(derived) != public_key.rstrip("="):
            # Browsers subscribed with the public key; a private key from another pair would have
            # every push refused (403). Stop at start-up instead.
            raise ValueError("VAPID_PRIVATE_KEY is not the pair of VAPID_PUBLIC_KEY")
        self._subject = subject
        self._timeout = timeout_seconds
        self._session = session or requests.Session()
        self._session.max_redirects = 0

    def send(self, target: PushTarget, data: str, *, ttl: int) -> None:
        try:
            webpush(
                subscription_info={
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=data,
                vapid_private_key=self._vapid,
                # A new dict each time: pywebpush writes the audience and expiry into it.
                vapid_claims={"sub": self._subject},
                ttl=ttl,
                timeout=self._timeout,
                headers={"Urgency": "normal"},
                requests_session=self._session,
            )
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            raise PushFailed(failure_for(status), status=status) from None
        except requests.TooManyRedirects:
            raise PushFailed(PushFailure.REFUSED) from None
        except requests.RequestException:
            raise PushFailed(PushFailure.UNAVAILABLE) from None
