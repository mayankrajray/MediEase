"""``messages`` (M5-P2, tenant-scoped like every clinic table, ADR-0003) and webhooks (M5-P3)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from types import MappingProxyType
from uuid import UUID

from sqlalchemy import Select, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from mediease_api.adapters.db.models.messages import MessageRow, WebhookEventRow
from mediease_api.adapters.db.models.patients import PatientRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.messaging.message import Channel, Message, MessageStatus, SourceType
from mediease_api.domain.messaging.webhook import WebhookEvent
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.ports.messaging import ChannelCost


def _write(row: MessageRow, message: Message) -> None:
    """The columns a message changes after it was prepared."""
    row.variables = dict(message.variables)
    row.to_phone_encrypted = message.to_phone_encrypted
    row.status = message.status.value
    row.error_code = message.error_code
    row.provider_message_id = message.provider_message_id
    row.job_id = message.job_id
    row.sending_started_at = message.sending_started_at
    row.sent_at = message.sent_at
    row.delivered_at = message.delivered_at
    row.read_at = message.read_at
    row.failed_at = message.failed_at
    row.pricing_category = message.pricing_category
    row.cost_millipaise = message.cost_millipaise
    row.updated_at = message.updated_at


def _from_row(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        clinic_id=row.clinic_id,
        patient_id=row.patient_id,
        source_type=SourceType(row.source_type),
        source_id=row.source_id,
        channel=Channel(row.channel),
        provider=row.provider,
        template_key=row.template_key,
        template_version=row.template_version,
        language=Language(row.language),
        variables=MappingProxyType({str(k): str(v) for k, v in row.variables.items()}),
        to_phone_encrypted=row.to_phone_encrypted,
        idempotency_key=row.idempotency_key,
        status=MessageStatus(row.status),
        error_code=row.error_code,
        provider_message_id=row.provider_message_id,
        request_id=row.request_id,
        job_id=row.job_id,
        sending_started_at=row.sending_started_at,
        sent_at=row.sent_at,
        failed_at=row.failed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        delivered_at=row.delivered_at,
        read_at=row.read_at,
        pricing_category=row.pricing_category,
        cost_millipaise=row.cost_millipaise,
    )


class SqlAlchemyMessageRepository(TenantScopedRepository[MessageRow]):
    model = MessageRow
    entity_name = "message"

    def add(self, message: Message) -> None:
        self._check_owned(message.clinic_id)
        row = MessageRow(
            id=message.id,
            clinic_id=self.clinic_id,
            patient_id=message.patient_id,
            source_type=message.source_type.value,
            source_id=message.source_id,
            channel=message.channel.value,
            provider=message.provider,
            template_key=message.template_key,
            template_version=message.template_version,
            language=message.language.value,
            idempotency_key=message.idempotency_key,
            request_id=message.request_id,
            created_at=message.created_at,
        )
        _write(row, message)
        self._session.add(row)
        self._session.flush()

    def update(self, message: Message) -> None:
        self._check_owned(message.clinic_id)
        _write(self._require_row(message.id), message)
        self._session.flush()

    def get_by_key(self, idempotency_key: str, *, for_update: bool = False) -> Message | None:
        query = self._scoped_select().where(MessageRow.idempotency_key == idempotency_key)
        return self._one(query, for_update)

    def get(self, message_id: UUID, *, for_update: bool = False) -> Message | None:
        return self._one(self._scoped_select().where(MessageRow.id == message_id), for_update)

    def list_for_patient(self, patient_id: UUID, *, limit: int) -> Sequence[Message]:
        query = (
            self._scoped_select()
            .where(MessageRow.patient_id == patient_id)
            .order_by(MessageRow.created_at.desc(), MessageRow.id.desc())
            .limit(limit)
        )
        return [_from_row(row) for row in self._session.scalars(query)]

    def _one(self, query: Select[MessageRow], for_update: bool) -> Message | None:
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _from_row(row) if row else None


class SqlAlchemyMessageLookup:
    """Which clinic a provider status is for (M5-P3): a reviewed cross-clinic read of two IDs.

    Our own ID (echoed back by the provider) wins; the provider's ID is the fallback. Nothing but
    the clinic and message IDs leaves this class.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find(
        self, *, message_id: UUID | None, provider_message_id: str
    ) -> tuple[UUID, UUID] | None:
        query = select(MessageRow.clinic_id, MessageRow.id)
        if message_id is not None:
            row = self._session.execute(query.where(MessageRow.id == message_id)).one_or_none()
            if row is not None:
                return row.clinic_id, row.id
        row = self._session.execute(
            query.where(MessageRow.provider_message_id == provider_message_id)
        ).one_or_none()
        return (row.clinic_id, row.id) if row is not None else None

    def count_unconfirmed(self, *, sent_before: datetime) -> int:
        query = select(func.count()).where(
            MessageRow.status == MessageStatus.SENT.value, MessageRow.sent_at < sent_before
        )
        return int(self._session.execute(query).scalar_one())


class SqlAlchemyOptOutLookup:
    """Who a STOP reply opts out (M5-P5 decision 2A): a reviewed cross-clinic read of IDs.

    In every clinic that has sent a message (``sent_at`` set) to a patient with this number, every
    patient whose current number it is: a family sharing one phone is opted out together (spec §8),
    and a clinic that never wrote to the number is left alone. Only clinic and patient IDs leave
    this class; ``ix_patients_phone_e164`` serves the number match and
    ``ix_messages_clinic_id_patient_id`` the check.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def patients_messaged(self, phone: PhoneNumber) -> Sequence[tuple[UUID, UUID]]:
        reached = aliased(PatientRow)
        clinic_wrote = (
            select(MessageRow.id)
            .join(
                reached,
                (reached.clinic_id == MessageRow.clinic_id) & (reached.id == MessageRow.patient_id),
            )
            .where(
                MessageRow.clinic_id == PatientRow.clinic_id,
                reached.phone_e164 == phone.e164,
                MessageRow.sent_at.is_not(None),
            )
            .exists()
        )
        query = (
            select(PatientRow.clinic_id, PatientRow.id)
            .where(PatientRow.phone_e164 == phone.e164, clinic_wrote)
            .order_by(PatientRow.clinic_id, PatientRow.id)
        )
        return [(row.clinic_id, row.id) for row in self._session.execute(query)]


class SqlAlchemyWebhookEventRepository:
    """``webhook_events``: platform data, stored once per body (M5-P3)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: WebhookEvent) -> bool:
        statement = (
            insert(WebhookEventRow)
            .values(
                id=event.id,
                provider=event.provider,
                event_key=event.event_key,
                payload=dict(event.payload),
                received_at=event.received_at,
            )
            .on_conflict_do_nothing(index_elements=["event_key"])
            .returning(WebhookEventRow.id)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None

    def get(self, event_id: UUID, *, for_update: bool = False) -> WebhookEvent | None:
        query = select(WebhookEventRow).where(WebhookEventRow.id == event_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        if row is None:
            return None
        return WebhookEvent(
            id=row.id,
            provider=row.provider,
            event_key=row.event_key,
            payload=row.payload,
            received_at=row.received_at,
            processed_at=row.processed_at,
            error_code=row.error_code,
        )

    def update(self, event: WebhookEvent) -> None:
        row = self._session.get(WebhookEventRow, event.id)
        if row is None:
            raise NotFound("webhook event")
        row.payload = dict(event.payload)  # M5-P5: a STOP sender's number is removed
        row.processed_at = event.processed_at
        row.error_code = event.error_code
        self._session.flush()

    def list_unprocessed(self, *, received_before: datetime, limit: int) -> Sequence[UUID]:
        query = (
            select(WebhookEventRow.id)
            .where(
                WebhookEventRow.processed_at.is_(None),
                WebhookEventRow.received_at < received_before,
            )
            .order_by(WebhookEventRow.received_at)
            .limit(limit)
        )
        return list(self._session.scalars(query))


# The month's bounds are taken in each clinic's time zone, so the comparison on sent_at stays a
# plain range that ix_messages_clinic_id_sent_at serves.
_MONTHLY_COSTS = text(
    """
    SELECT c.id AS clinic_id, c.name AS clinic_name, m.channel,
           count(*) AS messages, count(m.cost_millipaise) AS priced,
           coalesce(sum(m.cost_millipaise), 0) AS cost_millipaise
    FROM clinics c
    JOIN messages m ON m.clinic_id = c.id
     AND m.sent_at >= (CAST(:month AS date)::timestamp AT TIME ZONE c.timezone)
     AND m.sent_at < ((CAST(:month AS date) + interval '1 month')::timestamp
                      AT TIME ZONE c.timezone)
    GROUP BY c.id, c.name, m.channel
    ORDER BY c.name, c.id, m.channel
    """
)


class SqlAlchemyMessageCostReport:
    """The ops monthly totals (M5-P5 decision 7A): a reviewed cross-clinic read of sums only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def monthly(self, month: date) -> Sequence[ChannelCost]:
        return [
            ChannelCost(
                clinic_id=row.clinic_id,
                clinic_name=row.clinic_name,
                channel=Channel(row.channel),
                messages=int(row.messages),
                priced=int(row.priced),
                cost_millipaise=int(row.cost_millipaise),
            )
            for row in self._session.execute(_MONTHLY_COSTS, {"month": month.replace(day=1)})
        ]
