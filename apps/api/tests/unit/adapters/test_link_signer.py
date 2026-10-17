"""The patient link signer (spec prescriptions R9; M4-P5 decision 2A)."""

from __future__ import annotations

import pytest

from mediease_api.adapters.security.link_signer import HmacLinkSigner

KEYS = {"k2": b"b" * 32, "k1": b"a" * 32}


def test_the_first_key_signs_and_every_key_verifies() -> None:
    signer = HmacLinkSigner(KEYS)
    assert signer.current_key_id == "k2"
    mac1, mac2 = signer.mac("k1", b"msg"), signer.mac("k2", b"msg")
    assert mac1 is not None and mac2 is not None and mac1 != mac2
    assert len(mac1) == 16
    assert signer.mac("k1", b"msg") == mac1  # stable
    assert signer.mac("k1", b"msh") != mac1


def test_an_unknown_key_has_no_mac() -> None:
    assert HmacLinkSigner(KEYS).mac("k9", b"msg") is None


def test_keys_are_required_and_named_plainly() -> None:
    with pytest.raises(ValueError, match="at least one"):
        HmacLinkSigner({})
    with pytest.raises(ValueError, match="key ID"):
        HmacLinkSigner({"bad id": b"x" * 32})
