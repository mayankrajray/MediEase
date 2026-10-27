"""The upload lifecycle (M7b; spec prescription-uploads §3, R1, R9-R18)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from mediease_api.domain.shared.errors import InvalidTransition
from mediease_api.domain.uploads.errors import (
    NotAwaitingChallenge,
    NotVerified,
    SelectionRequired,
    UploadFileRejected,
)
from mediease_api.domain.uploads.upload import (
    GRANT_TTL,
    MAX_UPLOAD_BYTES,
    Access,
    Choice,
    PrescriptionUpload,
    Rejection,
    UploadSource,
    UploadState,
)
from tests.builders import new_id

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
PDF = b"%PDF-1.7\n" + b"0" * 32


def received() -> PrescriptionUpload:
    return PrescriptionUpload.receive(id=new_id(), account_id=new_id(), data=PDF, now=NOW)


def extracting() -> PrescriptionUpload:
    upload = received()
    upload.start_scan(NOW)
    upload.scanned_clean(NOW)
    return upload


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (None, "missing"),
        (b"", "missing"),
        (b"GIF89a", "type"),
        (b"%PDF-" + b"0" * MAX_UPLOAD_BYTES, "size"),
    ],
)
def test_r1_only_a_pdf_jpeg_or_png_up_to_10_mb_is_received(data: bytes | None, reason: str) -> None:
    with pytest.raises(UploadFileRejected) as refused:
        PrescriptionUpload.receive(id=new_id(), account_id=new_id(), data=data, now=NOW)
    assert refused.value.details == {"reason": reason}


def test_r1_a_received_file_is_quarantined_under_its_account() -> None:
    upload = received()
    assert upload.state is UploadState.QUARANTINED and upload.source is UploadSource.FILE
    assert upload.quarantine_key == f"uploads/{upload.account_id}/{upload.id}"
    assert (upload.content_type, upload.size_bytes) == ("application/pdf", len(PDF))


def test_r10_r17_an_own_record_verifies_and_the_file_key_goes() -> None:
    upload = extracting()
    rx, clinic = new_id(), new_id()
    upload.verify(access=Access.OWN, clinic_id=clinic, prescription_id=rx, current=True, now=NOW)
    assert upload.state is UploadState.VERIFIED and upload.quarantine_key is None
    assert upload.selected_id == rx and upload.expires_at == NOW + GRANT_TTL
    assert upload.usable_prescription(NOW) == rx
    with pytest.raises(NotVerified):
        upload.usable_prescription(NOW + GRANT_TTL)


def test_r15_a_superseded_version_waits_for_a_choice() -> None:
    upload = extracting()
    rx, latest = new_id(), new_id()
    upload.verify(access=Access.OWN, clinic_id=new_id(), prescription_id=rx, current=False, now=NOW)
    with pytest.raises(SelectionRequired):
        upload.usable_prescription(NOW)
    upload.choose(Choice.LATEST, latest_id=latest, now=NOW)
    assert upload.usable_prescription(NOW) == latest
    upload.choose(Choice.UPLOADED, latest_id=latest, now=NOW)
    assert upload.usable_prescription(NOW) == rx


def test_r11_r12_the_check_counts_down_and_the_fifth_failure_locks() -> None:
    upload = extracting()
    upload.needs_challenge(UUID(int=5), NOW)
    assert upload.quarantine_key is None and upload.candidate_id == UUID(int=5)
    assert [upload.challenge_failed(NOW) for _ in range(5)] == [4, 3, 2, 1, 0]
    assert (upload.state, upload.rejection_code) == (UploadState.REJECTED, Rejection.LOCKED)
    assert upload.candidate_id is None
    with pytest.raises(NotAwaitingChallenge):
        upload.challenge_failed(NOW)


def test_a_representative_verifies_only_from_the_check() -> None:
    upload = extracting()
    with pytest.raises(InvalidTransition):
        upload.verify(
            access=Access.REPRESENTATIVE,
            clinic_id=new_id(),
            prescription_id=new_id(),
            current=True,
            now=NOW,
        )


def test_r9_a_typed_code_has_no_file() -> None:
    upload = PrescriptionUpload.typed(id=new_id(), account_id=new_id(), now=NOW)
    assert (upload.state, upload.source, upload.quarantine_key) == (
        UploadState.EXTRACTING,
        UploadSource.CODE,
        None,
    )


def test_r17_withdrawing_clears_everything_and_is_idempotent() -> None:
    upload = extracting()
    upload.verify(
        access=Access.OWN, clinic_id=new_id(), prescription_id=new_id(), current=True, now=NOW
    )
    upload.withdraw(NOW)
    upload.withdraw(NOW)
    assert (upload.state, upload.rejection_code) == (UploadState.REJECTED, Rejection.WITHDRAWN)
    assert upload.prescription_id is None and upload.expires_at is None
    with pytest.raises(InvalidTransition):
        upload.reject(Rejection.INFECTED, NOW)


def test_r18_what_the_sweep_ends() -> None:
    fresh = received()
    assert fresh.stale(NOW + timedelta(minutes=59)) is None
    assert fresh.stale(NOW + timedelta(hours=1)) is Rejection.ABANDONED
    waiting = extracting()
    waiting.needs_challenge(UUID(int=1), NOW)
    assert waiting.stale(NOW + timedelta(hours=23)) is None
    assert waiting.stale(NOW + timedelta(hours=24)) is Rejection.EXPIRED
    done = extracting()
    done.verify(
        access=Access.OWN, clinic_id=new_id(), prescription_id=new_id(), current=True, now=NOW
    )
    assert done.stale(NOW + timedelta(days=2)) is None
