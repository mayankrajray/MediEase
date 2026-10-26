"""Visit attachments and the shared file sniffer (M6d-P6; FR-VIS-04; spec visit-attachments)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from mediease_api.domain.shared.files import FileProblem, sniff
from mediease_api.domain.visits.attachment import (
    FILENAME_MAX,
    MAX_ATTACHMENT_BYTES,
    AttachmentLocked,
    AttachmentNotYours,
    AttachmentRejected,
    VisitAttachment,
    attachment_key,
    clean_filename,
)
from tests.builders import NOW, new_id

PDF = b"%PDF-1.7\n" + b"0" * 4
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 4
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 4


def _upload(data: bytes | None = PDF, filename: str | None = "cbc.pdf") -> VisitAttachment:
    return VisitAttachment.upload(
        id=new_id(),
        clinic_id=new_id(),
        visit_id=new_id(),
        patient_id=new_id(),
        data=data,
        filename=filename,
        by=new_id(),
        now=NOW,
    )


@pytest.mark.parametrize(
    ("data", "found"),
    [
        (PDF, "application/pdf"),
        (JPEG, "image/jpeg"),
        (PNG, "image/png"),
        (None, FileProblem.MISSING),
        (b"", FileProblem.MISSING),
        (b"GIF89a", FileProblem.TYPE),
        (b"<html><script>", FileProblem.TYPE),
        (b"%PDF-" + b"0" * 12, FileProblem.SIZE),
    ],
)
def test_sniff_decides_by_first_bytes_and_size(data: bytes | None, found: str) -> None:
    assert sniff(data, max_bytes=16) == found


def test_fr_vis_04_r2_a_report_is_recognised_by_its_bytes_not_its_name() -> None:
    attachment = _upload(PNG, filename="report.pdf")
    assert attachment.content_type == "image/png"
    assert attachment.filename == "report.pdf.png"
    assert attachment.size_bytes == len(PNG)
    assert attachment.storage_key == attachment_key(
        attachment.clinic_id, attachment.visit_id, attachment.id
    )
    assert not attachment.is_shared and not attachment.is_deleted


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (None, FileProblem.MISSING),
        (b"MZ\x90\x00", FileProblem.TYPE),
        (b"%PDF-" + b"0" * MAX_ATTACHMENT_BYTES, FileProblem.SIZE),
    ],
)
def test_r2_missing_large_or_other_files_are_refused(
    data: bytes | None, reason: FileProblem
) -> None:
    with pytest.raises(AttachmentRejected) as raised:
        _upload(data)
    assert raised.value.reason is reason
    assert raised.value.details == {"reason": reason.value}


def test_r2_exactly_ten_megabytes_is_accepted() -> None:
    data = b"%PDF-" + b"0" * (MAX_ATTACHMENT_BYTES - 5)
    assert _upload(data).size_bytes == MAX_ATTACHMENT_BYTES


@pytest.mark.parametrize(
    ("raw", "content_type", "cleaned"),
    [
        ("C:\\scans\\HbA1c.pdf", "application/pdf", "HbA1c.pdf"),
        ("../../etc/passwd", "application/pdf", "passwd.pdf"),
        ("x-ray\x00\x1f  chest .JPG", "image/jpeg", "x-ray chest .JPG"),
        ("scan.jpeg", "image/jpeg", "scan.jpeg"),
        ("", "image/png", "report.png"),
        (None, "application/pdf", "report.pdf"),
        ("...", "application/pdf", "report.pdf"),
        ("रिपोर्ट.pdf", "application/pdf", "रिपोर्ट.pdf"),
    ],
)
def test_r5_file_names_are_cleaned(raw: str | None, content_type: str, cleaned: str) -> None:
    assert clean_filename(raw, content_type) == cleaned


def test_r5_long_names_keep_their_extension() -> None:
    name = clean_filename("a" * 300 + ".pdf", "application/pdf")
    assert len(name) == FILENAME_MAX and name.endswith(".pdf")


def test_r8_only_the_uploader_deletes_and_only_within_24_hours() -> None:
    attachment = _upload()
    other = new_id()
    assert attachment.can_delete(attachment.uploaded_by, NOW + timedelta(hours=23))
    assert not attachment.can_delete(other, NOW)
    assert not attachment.can_delete(attachment.uploaded_by, NOW + timedelta(hours=24))

    with pytest.raises(AttachmentNotYours):
        attachment.delete(by=other, now=NOW)
    with pytest.raises(AttachmentLocked) as locked:
        attachment.delete(by=attachment.uploaded_by, now=NOW + timedelta(hours=24))
    assert locked.value.details == {"locked_at": (NOW + timedelta(hours=24)).isoformat()}

    deleted = attachment.delete(by=attachment.uploaded_by, now=NOW + timedelta(hours=1))
    assert deleted.is_deleted and deleted.deleted_by == attachment.uploaded_by


def test_r10_sharing_is_recorded_and_repeating_it_changes_nothing() -> None:
    attachment = _upload()
    doctor = new_id()
    shared = attachment.share(True, by=doctor, now=NOW)
    assert (shared.shared_at, shared.shared_by) == (NOW, doctor)
    assert shared.share(True, by=new_id(), now=NOW + timedelta(hours=1)) is shared
    unshared = shared.share(False, by=doctor, now=NOW)
    assert (unshared.shared_at, unshared.shared_by) == (None, None)
    assert attachment.share(False, by=doctor, now=NOW) is attachment
