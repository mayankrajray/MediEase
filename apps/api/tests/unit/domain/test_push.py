"""M7e-E2 (ADR-0025; spec web-push R11-R13): what a push device may be."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from mediease_api.domain.push.subscription import (
    LABEL_MAX,
    PushOwner,
    PushSubscription,
    check_endpoint,
    check_keys,
    device_label,
    endpoint_digest,
)
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import NOW, new_id


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def point(seed: int) -> bytes:
    """A real uncompressed P-256 public key, the same for the same seed."""
    key = ec.derive_private_key(seed, ec.SECP256R1())
    return key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


P256DH = b64(point(7))
AUTH = b64(bytes(16))


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc:APA91b",
        "https://updates.push.services.mozilla.com/wpush/v2/gAAAA",
        "https://web.push.apple.com/QGuQyavXutnMH",
        "https://api.push.apple.com/3/device/x",
        "https://wns2-par02p.notify.windows.com/w/?token=x",
        "https://FCM.googleapis.com:443/fcm/send/x",
    ],
)
def test_r12_the_browsers_push_services_are_accepted(endpoint: str) -> None:
    assert check_endpoint(endpoint) == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/x",  # not https
        "https://localhost/push",  # the server's own network
        "https://127.0.0.1/push",
        "https://169.254.169.254/latest/meta-data",  # cloud metadata
        "https://10.0.0.5/push",
        "https://api:8000/api/v1/me",  # a compose service
        "https://example.com/push",  # any other site
        "https://push.apple.com.evil.example/x",  # a look-alike host
        "https://evilnotify.windows.com/x",  # suffix without the dot
        "https://.push.apple.com/x",  # the suffix alone
        "https://user:pw@fcm.googleapis.com/fcm/send/x",  # credentials in the URL
        "https://fcm.googleapis.com:8443/fcm/send/x",  # another port
        "https://fcm.googleapis.com:99999/x",  # a broken port
        "ftp://fcm.googleapis.com/x",
        "fcm.googleapis.com/fcm/send/x",
        "",
        "https://fcm.googleapis.com/" + "a" * 2100,
    ],
)
def test_r12_anything_else_is_refused_so_the_server_never_posts_elsewhere(endpoint: str) -> None:
    with pytest.raises(InvalidValue) as refused:
        check_endpoint(endpoint)
    assert refused.value.field == "endpoint"
    assert endpoint[:20] not in refused.value.message or not endpoint


def test_r13_keys_are_a_p256_point_and_a_16_byte_secret() -> None:
    assert check_keys(P256DH, AUTH) == (P256DH, AUTH)
    assert check_keys(P256DH + "=", AUTH + "==") == (P256DH + "=", AUTH + "==")


@pytest.mark.parametrize(
    ("p256dh", "auth", "field"),
    [
        (b64(b"\x02" + bytes(64)), AUTH, "keys.p256dh"),  # compressed or not a point
        (b64(b"\x04" + bytes(32)), AUTH, "keys.p256dh"),  # too short
        # M7e-E5: the right size and prefix, but not a point on the curve (found on a real device
        # test: such a key fails every send).
        (b64(b"\x04" + bytes(range(64))), AUTH, "keys.p256dh"),
        ("not base64!", AUTH, "keys.p256dh"),
        (P256DH, b64(bytes(15)), "keys.auth"),
        (P256DH, "a/b+c", "keys.auth"),  # standard base64, not base64url
        (P256DH, "A" * 200, "keys.auth"),
    ],
)
def test_r13_other_keys_are_refused(p256dh: str, auth: str, field: str) -> None:
    with pytest.raises(InvalidValue) as refused:
        check_keys(p256dh, auth)
    assert refused.value.field == field


@pytest.mark.parametrize(
    ("agent", "label"),
    [
        (
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
            "Chrome on Android",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Version/17.5 Mobile"
            " Safari/604.1",
            "Safari on iPhone",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0 Safari/537.36 Edg/131.0",
            "Edge on Windows",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Firefox on Linux",
        ),
        ("curl/8.0", "Browser"),
        (None, "Browser"),
    ],
)
def test_r15_a_device_is_named_from_a_fixed_vocabulary_never_the_raw_agent(
    agent: str | None, label: str
) -> None:
    assert device_label(agent) == label
    assert len(device_label("x" * 500)) <= LABEL_MAX


def test_the_endpoint_is_found_by_its_digest_and_stored_only_encrypted() -> None:
    digest = endpoint_digest("https://fcm.googleapis.com/fcm/send/abc")
    assert len(digest) == 64 and digest == endpoint_digest(
        "https://fcm.googleapis.com/fcm/send/abc"
    )
    owner = PushOwner.patient(new_id())
    device = PushSubscription.create(
        id=new_id(),
        owner=owner,
        digest=digest,
        endpoint_encrypted="enc-e",
        p256dh_encrypted="enc-p",
        auth_encrypted="enc-a",
        label="Chrome on Android",
        now=NOW,
    )
    assert device.is_active and device.created_at == device.updated_at == NOW
    assert "fcm.googleapis.com" not in repr(device)
