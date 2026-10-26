"""The printed verification code and its QR payload (M7a-P1; FR-RX-11; ADR-0023)."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from mediease_api.domain.prescriptions.prescription import CURRENT_LAYOUT
from mediease_api.domain.prescriptions.verification import (
    VERIFICATION_LAYOUT,
    codes_in_text,
    parse_payload,
    parse_typed_code,
    printed_code,
    qr_payload,
)
from tests.unit.domain.test_rx_document import document, issued

RX = UUID("0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d")
OTHER = UUID("0192f3a4-7c1e-7b2a-9d40-000000000001")


def test_fr_rx_11_new_issues_get_the_verification_layout() -> None:
    assert CURRENT_LAYOUT >= VERIFICATION_LAYOUT
    rx = issued()
    assert rx.layout_version == CURRENT_LAYOUT


def test_fr_rx_11_the_document_carries_the_versions_own_id_and_nothing_else() -> None:
    rx = issued()
    doc = document(rx)
    assert doc.verification_label == "Verification code"
    assert doc.verification_code == str(rx.id)
    assert doc.qr_payload == f"MEDIEASE-RX:1:{rx.id}"


def test_fr_rx_11_hindi_label() -> None:
    from mediease_api.domain.patients.patient import Language

    assert document(issued(Language.HI)).verification_label == "सत्यापन कोड"


def test_fr_rx_11_earlier_layouts_carry_no_code() -> None:
    rx = replace(issued(), layout_version=2)
    doc = document(rx)
    assert (doc.verification_label, doc.verification_code, doc.qr_payload) == ("", "", "")


def test_payload_and_printed_code_are_the_canonical_uuid() -> None:
    assert printed_code(RX) == "0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d"
    assert qr_payload(RX) == "MEDIEASE-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d"


@pytest.mark.parametrize(
    "payload",
    [
        "MEDIEASE-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d",
        "mediease-rx:1:0192F3A4-7C1E-7B2A-9D40-5E6F7A8B9C0D",
        "  MEDIEASE-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d\n",
    ],
)
def test_parse_payload_accepts_only_our_grammar(payload: str) -> None:
    assert parse_payload(payload) == RX


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d",  # a bare UUID is not our QR
        "MEDIEASE-RX:2:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d",  # unknown version
        "MEDIEASE-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0",  # too short
        "MEDIEASE-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0dX",
        "MEDIEASE-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d;patient=A",
        "https://example.invalid/?MEDIEASE-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d",
        "MEDIEASE-RX:1:" + "a" * 200,
        "OTHER-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d",
    ],
)
def test_parse_payload_refuses_malformed_or_foreign_payloads(payload: str) -> None:
    assert parse_payload(payload) is None


@pytest.mark.parametrize(
    "typed",
    [
        "0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d",
        "0192F3A4-7C1E-7B2A-9D40-5E6F7A8B9C0D",
        "0192f3a47c1e7b2a9d405e6f7a8b9c0d",
        " 0192f3a4-7c1e-7b2a- 9d40-5e6f7a8b9c0d ",
        "MEDIEASE-RX:1:0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d",
    ],
)
def test_parse_typed_code_accepts_the_printed_code_however_typed(typed: str) -> None:
    assert parse_typed_code(typed) == RX


@pytest.mark.parametrize("typed", ["", "ME-0142", "0192f3a4", "not a code", "x" * 500])
def test_parse_typed_code_refuses_anything_else(typed: str) -> None:
    assert parse_typed_code(typed) is None


def test_codes_in_text_finds_each_distinct_code_once() -> None:
    text = f"Verification code\n{RX}\nMEDIEASE-RX:1:{RX}\nPatient code: ME-0142"
    assert codes_in_text(text) == {RX}
    assert codes_in_text(f"{RX} and {OTHER}") == {RX, OTHER}
    assert codes_in_text("no codes here, ME-0142") == frozenset()
