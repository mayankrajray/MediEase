"""The upload worker's jobs (M7b-P7..P9; FR-UPL-02..05; spec R4-R8, R17, R18; NFR-20).

``ProcessUpload`` (``process_prescription_upload``) takes one upload through its states, each
move committed before the next stage so a crash resumes where it stopped:

1. **Scan** (``SCANNING``). The bytes go to the malware scanner before anything parses them. An
   infected file is rejected; an unreachable scanner is retried and, on the last attempt,
   rejected (``UPL_SCAN_UNAVAILABLE``). Never skipped.
2. **Read** (``EXTRACTING``). The identifier reader returns the MediEase IDs found and nothing
   else (R8). None: ``UPL_NO_IDENTIFIER``; several: ``UPL_AMBIGUOUS``; undecodable within the
   limits: ``UPL_UNREADABLE``.
3. **Verify.** One ID: the account's own record, or the last-4 check (``verify.py``).

Whatever the outcome, the file is deleted as the upload leaves extraction or is rejected, *before*
that state commits: a failed delete keeps the row pointing at the file, and the sweep tries again.

``SweepUploads`` (``purge_prescription_uploads``, every 10 minutes) rejects abandoned uploads and
expired checks, deleting their files, and deletes rows 30 days after creation (R18).

Logs carry the upload's ID, states, codes and counts; never the file name, a code, or anything
read from the file.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from mediease_api.application.uploads.verify import resolve_identified
from mediease_api.domain.jobs.job import ClaimedJob
from mediease_api.domain.jobs.retry import JobFailure
from mediease_api.domain.uploads.checks import ScannerUnavailable, UnreadableFile
from mediease_api.domain.uploads.upload import (
    ABANDON_AFTER,
    FILE_STATES,
    ROW_RETENTION,
    PrescriptionUpload,
    Rejection,
    UploadState,
)
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import UnitOfWork
from mediease_api.ports.uploads import IdentifierReaderPort, MalwareScannerPort

logger = structlog.get_logger(__name__)

SCAN_UNAVAILABLE = "UPL_SCAN_UNAVAILABLE"
SWEEP_BATCH = 200


class ProcessUpload:
    def __init__(
        self,
        *,
        uow: UnitOfWork,
        clock: ClockPort,
        ids: IdPort,
        storage: BlobStoragePort,
        scanner: MalwareScannerPort,
        reader: IdentifierReaderPort,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._storage = storage
        self._scanner = scanner
        self._reader = reader

    def __call__(self, job: ClaimedJob) -> None:
        upload_id = UUID(str(job.payload["upload_id"]))
        upload = self._begin(upload_id)
        if upload is None:
            return
        assert upload.quarantine_key is not None and upload.content_type is not None
        data = self._storage.get(upload.quarantine_key)
        if data is None:
            self._reject(upload_id, Rejection.FILE_MISSING)
            return
        if upload.state is UploadState.SCANNING and not self._scan(job, upload_id, data):
            return
        self._read_and_verify(upload_id, data, upload.content_type)

    def _begin(self, upload_id: UUID) -> PrescriptionUpload | None:
        """The upload moved into scanning (or already past it), or ``None`` if nothing is left."""
        with self._uow as uow:
            upload = uow.prescription_uploads.get(upload_id, for_update=True)
            if upload is None or upload.state not in FILE_STATES:
                return None  # done already (a retry after success, a withdrawal, the sweep)
            if upload.state in (UploadState.QUARANTINED, UploadState.SCANNING):
                upload.start_scan(self._clock.now())
                uow.prescription_uploads.update(upload)
                uow.commit()
            return upload

    def _scan(self, job: ClaimedJob, upload_id: UUID, data: bytes) -> bool:
        """R5: True when clean and moved on to reading; False when it ended here."""
        try:
            result = self._scanner.scan(data)
        except ScannerUnavailable:
            if job.attempts >= job.max_attempts:
                logger.error("upload.scan_unavailable", upload_id=str(upload_id), final=True)
                self._reject(upload_id, Rejection.SCAN_UNAVAILABLE)
                return False
            logger.warning(
                "upload.scan_unavailable", upload_id=str(upload_id), attempt=job.attempts
            )
            raise JobFailure(SCAN_UNAVAILABLE, retryable=True) from None
        if not result.clean:
            logger.warning(
                "upload.scanned",
                upload_id=str(upload_id),
                result="infected",
                signature=result.signature,
            )
            self._reject(upload_id, Rejection.INFECTED)
            return False
        with self._uow as uow:
            upload = uow.prescription_uploads.get(upload_id, for_update=True)
            if upload is None or upload.state is not UploadState.SCANNING:
                return False
            upload.scanned_clean(self._clock.now())
            uow.prescription_uploads.update(upload)
            uow.commit()
        logger.info("upload.scanned", upload_id=str(upload_id), result="clean")
        return True

    def _read_and_verify(self, upload_id: UUID, data: bytes, content_type: str) -> None:
        try:
            read = self._reader.read(data, content_type)
        except UnreadableFile:
            self._reject(upload_id, Rejection.UNREADABLE)
            return
        if not read.ids:
            self._reject(upload_id, Rejection.NO_IDENTIFIER)
            return
        if len(read.ids) > 1:
            self._reject(upload_id, Rejection.AMBIGUOUS)
            return
        (candidate,) = read.ids
        with self._uow as uow:
            upload = uow.prescription_uploads.get(upload_id, for_update=True)
            if upload is None or upload.state is not UploadState.EXTRACTING:
                return
            key = upload.quarantine_key
            now = self._clock.now()
            resolve_identified(uow, self._ids, upload, candidate, now)
            if key is not None:
                self._storage.delete(key)
            uow.prescription_uploads.update(upload)
            uow.commit()
        logger.info(
            "upload.identified",
            upload_id=str(upload_id),
            methods=sorted(m.value for m in read.methods),
            state=upload.state.value,
        )
        logger.info("upload.file_deleted", upload_id=str(upload_id))

    def _reject(self, upload_id: UUID, code: Rejection) -> None:
        with self._uow as uow:
            upload = uow.prescription_uploads.get(upload_id, for_update=True)
            if upload is None or upload.is_terminal:
                return
            key = upload.quarantine_key
            if key is not None:
                self._storage.delete(key)
            upload.reject(code, self._clock.now())
            uow.prescription_uploads.update(upload)
            uow.commit()
        logger.info("upload.rejected", upload_id=str(upload_id), code=code.value)


class SweepUploads:
    """R18: abandoned uploads and expired checks end; rows (and any file) go after 30 days."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, storage: BlobStoragePort) -> None:
        self._uow = uow
        self._clock = clock
        self._storage = storage

    def __call__(self, job: ClaimedJob) -> None:
        now = self._clock.now()
        ended = 0
        with self._uow as uow:
            for upload in uow.prescription_uploads.unfinished_before(
                now - ABANDON_AFTER, limit=SWEEP_BATCH
            ):
                code = upload.stale(now)
                if code is None:
                    continue
                if upload.quarantine_key is not None:
                    self._storage.delete(upload.quarantine_key)
                upload.reject(code, now)
                uow.prescription_uploads.update(upload)
                ended += 1
            keys = uow.prescription_uploads.delete_created_before(now - ROW_RETENTION)
            for key in keys:
                self._storage.delete(key)
            uow.commit()
        logger.info("upload.swept", ended=ended, deleted_rows_with_files=len(keys))
