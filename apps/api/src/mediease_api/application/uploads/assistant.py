"""A verified upload handed to the assistant (M7b-P10; FR-UPL-05, FR-AI-04; spec R16; ADR-0023).

This is the boundary the whole design rests on: the assistant gets an upload's **database**
prescription and nothing from the file. ``read_verified_upload`` takes the account's own verified,
unexpired upload with a chosen version, re-checks the access (``OWN``: still one of the account's
linked records; ``REPRESENTATIVE``: still the same prescription chain, the clinic not suspended),
reads that exact version from its clinic's tables and builds its page with the phrasebook. The
upload row holds IDs only and its file is long gone, so there is nothing else it could pass on.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from mediease_api.application.assistant.patient import ChosenPrescription
from mediease_api.application.portal.records import version_in_scope
from mediease_api.application.portal.scope import PortalScope
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.application.uploads.verify import own_upload
from mediease_api.domain.clinics.clinic import ClinicStatus
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.prescriptions.patient_view import build_version_page
from mediease_api.domain.prescriptions.prescription import PrescriptionStatus
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.uploads.upload import Access
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


class ReadVerifiedUpload:
    """``UploadReader`` for ``PatientAssistant``: the chosen version of a verified upload."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def __call__(
        self, principal: PatientPrincipal, upload_id: UUID, language: Language
    ) -> ChosenPrescription:
        with self._uow as uow:
            upload = own_upload(uow, principal, upload_id)
            selected = upload.usable_prescription(self._clock.now())
            assert upload.clinic_id is not None and upload.prescription_id is not None
            clinic = uow.clinics.get(upload.clinic_id)
            if clinic is None or clinic.status is ClinicStatus.SUSPENDED:
                raise NotFound("upload")
            if upload.access is Access.OWN:
                found = version_in_scope(PortalScope.read(uow, principal.account_id), selected)
                if found is None:  # unlinked since: the grant follows the link
                    logger.info("portal.not_found", entity="upload", entity_id=str(upload_id))
                    raise NotFound("upload")
                _, rx = found
            else:
                tenant = uow.tenant(upload.clinic_id)
                rx_found = tenant.prescriptions.get(selected)
                uploaded = tenant.prescriptions.get(upload.prescription_id)
                if (
                    rx_found is None
                    or uploaded is None
                    or rx_found.visit_id != uploaded.visit_id  # the same chain only (R14)
                    or rx_found.status
                    not in (PrescriptionStatus.ISSUED, PrescriptionStatus.SUPERSEDED)
                ):
                    raise NotFound("upload")
                rx = rx_found
            page = build_version_page(rx, language=language, timezone=clinic.timezone)
        return ChosenPrescription(
            page,
            historical=rx.status is PrescriptionStatus.SUPERSEDED,
            ids={"upload_id": str(upload_id), "prescription_id": str(rx.id)},
        )
