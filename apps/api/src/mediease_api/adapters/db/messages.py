"""The ``messages`` repository (M5-P2), tenant-scoped like every clinic table (ADR-0003)."""

from __future__ import annotations

from types import MappingProxyType

from mediease_api.adapters.db.models.messages import MessageRow
from mediease_api.adapters.db.tenancy import TenantScopedRepository
from mediease_api.domain.messaging.message import Channel, Message, MessageStatus, SourceType
from mediease_api.domain.patients.patient import Language


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
    row.failed_at = message.failed_at
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
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self._session.scalars(query).one_or_none()
        return _from_row(row) if row else None
