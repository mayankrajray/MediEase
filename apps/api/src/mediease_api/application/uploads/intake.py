"""Receiving an upload or a typed code (M7b-P6, P9; FR-UPL-01, NFR-20; spec R1, R2, R9).

A file is recognised by its bytes, written write-once to the quarantine prefix, recorded as
``QUARANTINED`` and handed to the upload worker in the same transaction (the outbox); if the
commit fails the file is removed again. Nothing reads the file here. A typed code has no file and
is resolved at once (``verify.resolve_identified``).
"""

from __future__ import annotations

import structlog

from mediease_api.application.context import RequestInfo
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.application.uploads.verify import UploadView, limit, resolve_identified, view_of
from mediease_api.domain.jobs.job import PROCESS_UPLOAD_KIND, NewJob
from mediease_api.domain.prescriptions.verification import parse_typed_code
from mediease_api.domain.shared.errors import InvalidValue
from mediease_api.domain.uploads.errors import TooManyUploads, UploadFailed
from mediease_api.domain.uploads.upload import MAX_IN_FLIGHT, PrescriptionUpload
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.storage import BlobStoragePort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

# Scan attempts: 1, 5 and 15 minutes apart (domain/jobs/retry.py), then UPL_SCAN_UNAVAILABLE.
PROCESS_MAX_ATTEMPTS = 4


class UploadPrescription:
    def __init__(
        self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort, storage: BlobStoragePort
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids
        self._storage = storage

    def execute(
        self, principal: PatientPrincipal, data: bytes | None, info: RequestInfo
    ) -> UploadView:
        limit(self._uow, self._clock, info, principal.account_id, "upload")
        stored: str | None = None
        try:
            with self._uow as uow:
                if uow.prescription_uploads.count_in_flight(principal.account_id) >= MAX_IN_FLIGHT:
                    raise TooManyUploads()
                now = self._clock.now()
                upload = PrescriptionUpload.receive(
                    id=self._ids.new_id(), account_id=principal.account_id, data=data, now=now
                )
                assert data is not None and upload.quarantine_key and upload.content_type
                try:
                    self._storage.put(upload.quarantine_key, data, content_type=upload.content_type)
                except Exception:
                    logger.warning("upload.store_failed", upload_id=str(upload.id))
                    raise UploadFailed() from None
                stored = upload.quarantine_key
                uow.prescription_uploads.add(upload)
                uow.jobs.enqueue(
                    NewJob.create(
                        id=self._ids.new_id(),
                        kind=PROCESS_UPLOAD_KIND,
                        now=now,
                        payload={"upload_id": str(upload.id)},
                        max_attempts=PROCESS_MAX_ATTEMPTS,
                        request_id=info.request_id,
                        dedupe_key=f"upload:{upload.id}",
                    )
                )
                uow.commit()
                stored = None
                view = view_of(uow, upload)
        finally:
            if stored is not None:
                try:
                    self._storage.delete(stored)
                except Exception:
                    logger.warning("upload.cleanup_failed", exc_info=True)
        logger.info(
            "upload.received",
            upload_id=str(view.id),
            content_type=upload.content_type,
            size_bytes=upload.size_bytes,
        )
        return view


class TypePrescriptionCode:
    """R9: the printed code typed (or pasted); verified at once, no file, no scan."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(self, principal: PatientPrincipal, code: str, info: RequestInfo) -> UploadView:
        candidate = parse_typed_code(code)
        if candidate is None:
            raise InvalidValue("code", "is not a MediEase verification code")
        limit(self._uow, self._clock, info, principal.account_id, "upload")
        with self._uow as uow:
            now = self._clock.now()
            upload = PrescriptionUpload.typed(
                id=self._ids.new_id(), account_id=principal.account_id, now=now
            )
            resolve_identified(uow, self._ids, upload, candidate, now, info)
            uow.prescription_uploads.add(upload)
            uow.commit()
            logger.info("upload.identified", upload_id=str(upload.id), method="CODE")
            return view_of(uow, upload)
