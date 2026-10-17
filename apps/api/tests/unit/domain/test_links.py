"""Patient links and their tokens (spec prescriptions R9, R10; AC3; M4-P5 decisions 1A, 2A)."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import pytest

from mediease_api.domain.links import token as tokens
from mediease_api.domain.links.errors import (
    LinkExpired,
    LinkInvalid,
    LinkLocked,
    LinkNotLocked,
    LinkRevoked,
)
from mediease_api.domain.links.link import MAX_FAILED_CHALLENGES, LinkPurpose, PatientLink
from mediease_api.domain.links.token import Kind, LinkClaims, ViewClaims
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import new_id

NOW = datetime(2026, 10, 19, 5, 0, 30, 123456, tzinfo=UTC)
KEY = b"k" * 32


def a_link(**overrides: object) -> PatientLink:
    fields: dict[str, object] = {
        "id": new_id(),
        "clinic_id": new_id(),
        "patient_id": new_id(),
        "prescription_id": new_id(),
        "key_id": "k1",
        "ttl_days": 90,
        "created_by": new_id(),
        "now": NOW,
    }
    fields.update(overrides)
    return PatientLink.create(**fields)  # type: ignore[arg-type]


def _mac(message: bytes) -> bytes:
    return hmac.new(KEY, message, hashlib.sha256).digest()[:16]


def link_token(claims: LinkClaims, key_id: str = "k1") -> str:
    signing = tokens.signing_input(Kind.LINK, key_id, tokens.link_claims_bytes(claims))
    return tokens.assemble(signing, _mac(signing))


def claims_of(link: PatientLink) -> LinkClaims:
    return LinkClaims(
        jti=link.id,
        cid=link.clinic_id,
        rid=link.prescription_id,
        purpose=link.purpose,
        exp=link.expires_at,
    )


# --- The link (R10, AC3) -----------------------------------------------------------------------


def test_r9_a_new_link_lasts_90_days_in_whole_seconds() -> None:
    link = a_link()
    assert link.purpose is LinkPurpose.RX_VIEW
    assert link.expires_at == (NOW + timedelta(days=90)).replace(microsecond=0)
    assert (link.failed_challenges, link.open_count, link.is_locked) == (0, 0, False)
    with pytest.raises(InvalidValue):
        a_link(ttl_days=91)


def test_ac3_five_wrong_answers_lock_the_link_until_staff_reset_it() -> None:
    link = a_link()
    left = [link.record_failure(NOW) for _ in range(MAX_FAILED_CHALLENGES)]
    assert left == [4, 3, 2, 1, 0]
    assert link.is_locked and link.locked_at == NOW
    with pytest.raises(LinkLocked):
        link.record_failure(NOW)
    with pytest.raises(LinkLocked):
        link.record_open(NOW)  # the right digits too (AC3)
    link.reset(NOW)
    assert (link.is_locked, link.failed_challenges) == (False, 0)
    with pytest.raises(LinkNotLocked):
        link.reset(NOW)


def test_r13_a_right_answer_clears_the_count_and_is_one_open() -> None:
    link = a_link()
    link.record_failure(NOW)
    link.record_open(NOW + timedelta(minutes=1))
    assert (link.failed_challenges, link.open_count) == (0, 1)
    assert link.last_opened_at == NOW + timedelta(minutes=1)


def test_revoked_and_expired_links_are_not_usable() -> None:
    link = a_link()
    link.check_usable(NOW)
    with pytest.raises(LinkExpired):
        link.check_usable(link.expires_at)
    link.revoke(NOW)
    with pytest.raises(LinkRevoked):
        link.check_usable(NOW)


def test_r10_a_view_lasts_30_minutes_but_never_past_the_link() -> None:
    link = a_link()
    assert link.view_expiry(NOW) == NOW + timedelta(minutes=30)
    assert link.view_expiry(link.expires_at - timedelta(minutes=5)) == link.expires_at


# --- Tokens (R9, decision 2A) --------------------------------------------------------------------


def test_r9_a_link_token_round_trips_its_claims_and_is_short() -> None:
    link = a_link()
    token = link_token(claims_of(link))
    assert len(token) <= 104  # a 2-character key ID gives 101
    parts = tokens.split(token)
    assert (parts.kind, parts.key_id) == (Kind.LINK, "k1")
    assert hmac.compare_digest(parts.mac, _mac(parts.signing_input))
    assert tokens.read_link_claims(parts) == claims_of(link)


def test_a_view_token_round_trips_and_is_never_a_link() -> None:
    claims = ViewClaims(jti=new_id(), exp=NOW.replace(microsecond=0))
    signing = tokens.signing_input(Kind.VIEW, "k1", tokens.view_claims_bytes(claims))
    parts = tokens.split(tokens.assemble(signing, _mac(signing)))
    assert tokens.read_view_claims(parts) == claims
    with pytest.raises(LinkInvalid):
        tokens.read_link_claims(parts)
    link_parts = tokens.split(link_token(claims_of(a_link())))
    with pytest.raises(LinkInvalid):
        tokens.read_view_claims(link_parts)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "a.b",
        "a.b.c.d",
        "!!!.AAAA.AAAA",
        "AQE.AAAA.AAAA",  # header without a key ID
        "x" * 300,
    ],
)
def test_malformed_tokens_are_invalid(bad: str) -> None:
    with pytest.raises(LinkInvalid):
        tokens.split(bad)


def test_a_changed_character_changes_the_mac_input_or_breaks_the_shape() -> None:
    token = link_token(claims_of(a_link()))
    header, claims, mac = token.split(".")
    flipped = claims[:-2] + ("A" if claims[-2] != "A" else "B") + claims[-1]
    parts = tokens.split(f"{header}.{flipped}.{mac}")
    assert not hmac.compare_digest(parts.mac, _mac(parts.signing_input))


def test_key_ids_are_short_and_plain() -> None:
    with pytest.raises(ValueError, match="key ID"):
        tokens.signing_input(Kind.LINK, "has space", b"")
    with pytest.raises(ValueError, match="key ID"):
        tokens.signing_input(Kind.LINK, "k" * 17, b"")


def test_describe_shows_claims_and_says_the_signature_was_not_checked() -> None:
    link = a_link()
    shown = tokens.describe(link_token(claims_of(link)))
    assert shown["signature"] == "not checked"
    assert (shown["kind"], shown["purpose"], shown["jti"]) == ("LINK", "RX_VIEW", str(link.id))
    assert shown["exp"] == link.expires_at.isoformat()
