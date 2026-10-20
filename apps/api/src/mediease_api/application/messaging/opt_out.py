"""Opting out by replying STOP (M5-P5; FR-MSG-05; spec R14, AC5; decisions 1A, 2A, 3A).

``OptOutByReply`` runs inside the webhook's processing job, in its transaction:

- the sender's number is decrypted from the stored payload, or, when WhatsApp hid it (a username),
  read from our message the reply answered (``context_id``);
- every patient with that number in each clinic that has messaged the number, in any clinic (the
  reviewed ``opt_out_lookup``; a family sharing a phone goes together), is opted out through their
  clinic's repository, with a SYSTEM
  ``patient.opted_out`` audit event (source ``inbound_message``); already opted out changes nothing;
- each such clinic gets one ``send_opt_out_confirmation`` job per STOP, keyed by the clinic and the
  inbound message (3A); a repeated STOP is answered again;
- no number or no patient: ``WH_STOP_UNMATCHED`` is logged and nothing changes.

The patient's consent flags stay as they were; ``opted_out_at`` alone stops every send, so the
next reminder becomes ``SKIPPED_NO_CONSENT`` (AC5).

``SendOptOutConfirmation`` sends ``opt_out_confirmed`` (a service reply inside the window the STOP
opened) even though the patient is now opted out; a job that runs more than 24 hours after the
STOP sends nothing (``MSG_NOT_APPLICABLE``).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.messaging.sender import MessageSender, Send, Skip
from mediease_api.application.patients.consent import ENTITY_TYPE, OptOutSource
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.jobs.job import ClaimedJob, NewJob
from mediease_api.domain.messaging.errors import MSG_NOT_APPLICABLE, WH_STOP_UNMATCHED
from mediease_api.domain.messaging.jobs import (
    OPT_OUT_CONFIRMATION_KIND,
    OPT_OUT_CONFIRMED,
    opt_out_confirmation_key,
)
from mediease_api.domain.messaging.message import SourceType
from mediease_api.domain.messaging.opt_out import InboundOptOut
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.shared.time import require_utc
from mediease_api.ports.ids import IdPort
from mediease_api.ports.messaging import PhoneCipherPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

# The customer-service window a patient's message opens (WhatsApp).
SERVICE_WINDOW = timedelta(hours=24)


class OptOutByReply:
    def __init__(self, *, ids: IdPort, phones: PhoneCipherPort) -> None:
        self._ids = ids
        self._phones = phones

    def apply(
        self, uow: UnitOfWork, stop: InboundOptOut, *, request_id: str | None, now: datetime
    ) -> bool:
        """True if at least one patient matched; the caller commits."""
        phone = self._sender(uow, stop)
        matches = uow.opt_out_lookup.patients_messaged(phone) if phone is not None else []
        if not matches:
            logger.info(
                "webhook.stop_unmatched",
                code=WH_STOP_UNMATCHED,
                had_number=stop.has_phone,
                had_context=stop.context_id is not None,
            )
            return False
        by_clinic: dict[UUID, list[UUID]] = defaultdict(list)
        for clinic_id, patient_id in matches:
            by_clinic[clinic_id].append(patient_id)
        for clinic_id, patient_ids in by_clinic.items():
            tenant = uow.tenant(clinic_id)
            for patient_id in patient_ids:
                self._opt_out(uow, tenant, patient_id, request_id=request_id, now=now)
            uow.jobs.enqueue(
                NewJob.create(
                    id=self._ids.new_id(),
                    kind=OPT_OUT_CONFIRMATION_KIND,
                    now=now,
                    clinic_id=clinic_id,
                    payload={
                        "patient_id": str(patient_ids[0]),
                        "inbound_message_id": stop.provider_message_id,
                        "received_at": stop.at.isoformat(),
                    },
                    request_id=request_id,
                    dedupe_key=opt_out_confirmation_key(clinic_id, stop.provider_message_id),
                )
            )
        return True

    def _sender(self, uow: UnitOfWork, stop: InboundOptOut) -> PhoneNumber | None:
        if stop.phone_encrypted is not None:
            return self._phones.decrypt(stop.phone_encrypted)
        if stop.context_id is None:
            return None
        found = uow.message_lookup.find(message_id=None, provider_message_id=stop.context_id)
        if found is None:
            return None
        clinic_id, message_id = found
        message = uow.tenant(clinic_id).messages.get(message_id)
        return self._phones.decrypt(message.to_phone_encrypted) if message is not None else None

    def _opt_out(
        self,
        uow: UnitOfWork,
        tenant: TenantRepositories,
        patient_id: UUID,
        *,
        request_id: str | None,
        now: datetime,
    ) -> None:
        patient = tenant.patients.get(patient_id, for_update=True)
        if patient is None or not patient.opt_out(now=now):
            return
        tenant.patients.update(patient)
        uow.audit.record(
            AuditEvent.record(
                id=self._ids.new_id(),
                action=AuditAction.PATIENT_OPTED_OUT,
                actor_type=ActorType.SYSTEM,
                now=now,
                clinic_id=tenant.clinic_id,
                entity_type=ENTITY_TYPE,
                entity_id=patient.id,
                request_id=request_id,
                metadata={"source": OptOutSource.INBOUND_MESSAGE.value},
            )
        )
        # Spec §7 analytics event `patient_opted_out`: a log event until M6 counts it.
        logger.info(
            "patient.opted_out",
            clinic_id=str(tenant.clinic_id),
            patient_id=str(patient.id),
            source=OptOutSource.INBOUND_MESSAGE.value,
            analytics="patient_opted_out",
        )


class SendOptOutConfirmation:
    def __init__(self, *, sender: MessageSender) -> None:
        self._sender = sender

    def __call__(self, job: ClaimedJob) -> None:
        assert job.clinic_id is not None
        patient_id = UUID(str(job.payload["patient_id"]))
        inbound_id = str(job.payload["inbound_message_id"])
        received_at = require_utc(
            datetime.fromisoformat(str(job.payload["received_at"])), "received_at"
        )

        def plan(uow: UnitOfWork, tenant: TenantRepositories, now: datetime) -> Send | Skip:
            if now - received_at > SERVICE_WINDOW:
                return Skip("service_window_closed", MSG_NOT_APPLICABLE)
            patient = tenant.patients.get(patient_id)
            clinic = uow.clinics.get(tenant.clinic_id)
            if patient is None or clinic is None:  # pragma: no cover - rows are never deleted
                return Skip("not_found", MSG_NOT_APPLICABLE)
            return Send(
                patient=patient,
                template_key=OPT_OUT_CONFIRMED,
                variables={"clinic_name": clinic.name},
                source_type=SourceType.OPT_OUT,
                source_id=patient.id,
            )

        self._sender.send(job, key=opt_out_confirmation_key(job.clinic_id, inbound_id), plan=plan)
