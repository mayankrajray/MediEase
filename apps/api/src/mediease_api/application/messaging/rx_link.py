"""Sending a prescription's link (FR-RX-06, FR-RX-09; prescriptions spec R14, R15; M5-P2).

Enqueued when a version is issued with ``link_delivery = PENDING``, in the issue's transaction.
Version 1 sends ``rx_ready``, a revision ``rx_updated``; both carry the chain's one link, rebuilt
from its row at send time so a link replaced since issue is never sent stale.

R15: the link goes only while the version is still ``PENDING`` (a newer version supersedes it),
within the send window of issue (24 hours at most) and while the patient allows WhatsApp. A
version too old, without consent or without an active link is marked ``EXPIRED``, audited as
SYSTEM, and nothing is sent; so turning M5 on never messages about M4-era prescriptions.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import structlog

from mediease_api.application.links.use_cases import LinkTokens
from mediease_api.application.messaging.sender import MessageSender, Send, Skip
from mediease_api.domain.audit.actions import AuditAction
from mediease_api.domain.audit.event import ActorType, AuditEvent
from mediease_api.domain.jobs.job import ClaimedJob, NewJob
from mediease_api.domain.links.errors import LinkInvalid
from mediease_api.domain.messaging.errors import MSG_NO_CONSENT, MSG_NOT_APPLICABLE
from mediease_api.domain.messaging.jobs import RX_LINK_KIND, RX_READY, RX_UPDATED, rx_link_key
from mediease_api.domain.messaging.message import SourceType
from mediease_api.domain.prescriptions.prescription import LinkDelivery, Prescription
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)


def enqueue_rx_link(
    uow: UnitOfWork, *, ids: IdPort, rx: Prescription, request_id: str | None, now: datetime
) -> bool:
    """In the issue's transaction (the outbox); only a version whose link is pending."""
    if rx.link_delivery is not LinkDelivery.PENDING:
        return False
    return uow.jobs.enqueue(
        NewJob.create(
            id=ids.new_id(),
            kind=RX_LINK_KIND,
            now=now,
            clinic_id=rx.clinic_id,
            payload={"prescription_id": str(rx.id)},
            request_id=request_id,
            dedupe_key=rx_link_key(rx.id),
        )
    )


class SendRxLink:
    def __init__(
        self,
        *,
        sender: MessageSender,
        ids: IdPort,
        tokens: LinkTokens,
        public_base_url: str,
        window: timedelta,
    ) -> None:
        self._sender = sender
        self._ids = ids
        self._tokens = tokens
        self._base_url = public_base_url.rstrip("/")
        self._window = window

    def __call__(self, job: ClaimedJob) -> None:
        rx_id = UUID(str(job.payload["prescription_id"]))

        def plan(uow: UnitOfWork, tenant: TenantRepositories, now: datetime) -> Send | Skip:
            rx = tenant.prescriptions.get(rx_id, for_update=True)
            if rx is None or rx.link_delivery is not LinkDelivery.PENDING:
                return Skip("not_pending", MSG_NOT_APPLICABLE)
            patient = tenant.patients.get(rx.patient_id)
            assert patient is not None  # a foreign key keeps it
            url: str | None = None
            requested = rx.link_delivery_requested_at
            if requested is None or now - requested > self._window:
                reason = "too_old"
            elif not patient.may_receive_whatsapp:
                reason = "no_consent"
            else:
                url = self._url(tenant, rx, now)
                reason = "no_link"
            if url is None:
                self._expire(uow, tenant, rx, reason, job.request_id, now)
                return Skip(
                    reason, MSG_NO_CONSENT if reason == "no_consent" else MSG_NOT_APPLICABLE
                )
            clinic = uow.clinics.get(tenant.clinic_id)
            assert clinic is not None
            return Send(
                patient=patient,
                template_key=RX_READY if rx.version == 1 else RX_UPDATED,
                variables={"clinic_name": clinic.name, "link": url},
                source_type=SourceType.PRESCRIPTION,
                source_id=rx.id,
            )

        def after_sent(uow: UnitOfWork, tenant: TenantRepositories, now: datetime) -> None:
            rx = tenant.prescriptions.get(rx_id, for_update=True)
            # Superseded while the call was under way: the newer version's own job sends it.
            if rx is not None and rx.link_delivery is LinkDelivery.PENDING:
                rx.link_sent(now)
                tenant.prescriptions.update(rx)

        self._sender.send(job, key=rx_link_key(rx_id), plan=plan, after_sent=after_sent)

    def _url(self, tenant: TenantRepositories, rx: Prescription, now: datetime) -> str | None:
        """The chain's active link (named by version 1), or None."""
        first_id = rx.id
        if rx.version != 1:
            first_id = next(
                v.id for v in tenant.prescriptions.list_for_visit(rx.visit_id) if v.version == 1
            )
        link = tenant.patient_links.active_for_prescription(first_id)
        if link is None or link.expires_at <= now:
            return None
        try:
            return f"{self._base_url}/p/{self._tokens.link_token(link)}"
        except LinkInvalid:  # its signing key was removed from the configuration
            return None

    def _expire(
        self,
        uow: UnitOfWork,
        tenant: TenantRepositories,
        rx: Prescription,
        reason: str,
        request_id: str | None,
        now: datetime,
    ) -> None:
        rx.link_expired(now)
        tenant.prescriptions.update(rx)
        uow.audit.record(
            AuditEvent.record(
                id=self._ids.new_id(),
                action=AuditAction.PRESCRIPTION_LINK_EXPIRED,
                actor_type=ActorType.SYSTEM,
                now=now,
                clinic_id=rx.clinic_id,
                entity_type="prescription",
                entity_id=rx.id,
                request_id=request_id,
                metadata={"version": str(rx.version), "reason": reason},
            )
        )
        logger.info("prescription.link_expired", prescription_id=str(rx.id), reason=reason)
