"""Explanations from the record and signed proposals (M7a-P3; FR-AI-01, 04; R7, R8, R10)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mediease_api.adapters.security.proposal_signer import HmacProposalSigner
from mediease_api.domain.assistant.explain import explain
from mediease_api.domain.assistant.proposal import (
    CallerKind,
    Proposal,
    ProposalInvalid,
)
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.patient_view import build_patient_view
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import new_id
from tests.unit.domain.test_rx_document import issued

NOW = datetime(2026, 10, 27, 10, 0, 7, tzinfo=UTC)


def _page(language: Language = Language.EN):  # type: ignore[no-untyped-def]
    rx = issued(language)
    page = build_patient_view([rx], language=language, timezone="Asia/Kolkata")
    assert page is not None
    return page


def test_fr_ai_04_the_explanation_is_the_pages_own_lines() -> None:
    page = _page()
    result = explain(page)
    assert result.text.startswith(f"This is what {page.doctor_name} wrote on")
    for field in page.medicines[0].fields:
        assert f"   - {field.label}: {field.value}" in result.text
    assert "1. Syrup X" in result.text
    assert "plenty of fluids" in result.text
    assert "5" in result.numbers
    assert "Syrup X" in result.own_words


def test_fr_ai_04_one_medicine_and_a_missing_number() -> None:
    page = _page()
    assert "Advice" not in explain(page, medicine_number=1).text
    missing = explain(page, medicine_number=9).text
    assert "Medicine 9 is not on it" in missing and "Syrup X" not in missing


def test_fr_ai_04_a_historical_version_says_so_and_hindi_reads_hindi() -> None:
    assert explain(_page(), historical=True).text.startswith("This is an older version")
    assert "ने" in explain(_page(Language.HI)).text.split("\n")[0]


def _proposal(**overrides: object) -> Proposal:
    fields: dict[str, object] = {
        "jti": new_id(),
        "caller": CallerKind.PATIENT,
        "subject": new_id(),
        "clinic_id": None,
        "action": "request_booking",
        "args": {"clinic_slug": "alpha"},
        "now": NOW,
    }
    fields.update(overrides)
    return Proposal.create(**fields)  # type: ignore[arg-type]


def test_r7_a_proposal_round_trips_and_expires_after_ten_minutes() -> None:
    proposal = _proposal()
    again = Proposal.decode(proposal.encode())
    assert again == proposal
    assert again.expires_at - again.issued_at == timedelta(minutes=10)
    again.check(caller=CallerKind.PATIENT, subject=proposal.subject, clinic_id=None, now=NOW)
    with pytest.raises(ProposalInvalid):
        again.check(
            caller=CallerKind.PATIENT,
            subject=proposal.subject,
            clinic_id=None,
            now=NOW + timedelta(minutes=10),
        )


def test_r8_a_proposal_names_its_caller_and_clinic() -> None:
    proposal = _proposal()
    for caller, subject, clinic in (
        (CallerKind.PATIENT, new_id(), None),
        (CallerKind.STAFF, proposal.subject, new_id()),
    ):
        with pytest.raises(ProposalInvalid):
            proposal.check(caller=caller, subject=subject, clinic_id=clinic, now=NOW)
    with pytest.raises(InvalidValue):
        _proposal(caller=CallerKind.STAFF)  # staff proposals carry the clinic
    with pytest.raises(InvalidValue):
        _proposal(args={"x": "y" * 201})
    with pytest.raises(ProposalInvalid):
        Proposal.decode(b"not json")


def test_r7_the_signer_detects_any_change_and_other_keys() -> None:
    signer = HmacProposalSigner("k" * 40)
    token = signer.sign(b'{"a":1}')
    assert signer.open(token) == b'{"a":1}'
    body, mac = token.split(".")
    assert signer.open(f"{body}x.{mac}") is None
    assert signer.open(f"{body}.{mac[:-2]}AA") is None
    assert signer.open("no-dot") is None
    assert signer.open("a" * 5000) is None
    assert HmacProposalSigner("j" * 40).open(token) is None
    with pytest.raises(ValueError):
        HmacProposalSigner("short")
