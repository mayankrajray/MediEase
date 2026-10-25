"""Patient notifications: delivery, the bell and preferences (M6b-P6; portal spec R55-R68).

**Recipients (R56)** are only ever the account a booking request belongs to, or the account
actively linked to the record an appointment or prescription is for: never found by phone, email
or name. **Delivery** inserts a row per notice; ``(account_id, event_key)`` is unique in the
database, so a replay writes nothing (R58). A kind turned off in the app writes no row. The four
booking kinds may also go by email to a verified address (R63), by a job keyed on the notice, so
it is sent at most once; the email never carries the reason or note.

Reads go through ``uow.patient_notification_lookup`` with the account's linked clinics (the
portal scope): an unlinked or suspended clinic's notices are neither listed nor counted (R60).
Titles are rendered here, in the account's language, from the clinic's own rows (R55, R59).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog

from mediease_api.application.portal.scope import PortalScope
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.domain.jobs.job import PATIENT_EMAIL_KIND, NewJob
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.notifications import (
    BOOKING_KINDS,
    Names,
    PatientChannel,
    PatientNotification,
    PatientNotificationKind,
    check_channel,
    render_title,
)
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.patient_notifications import PatientPreference
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork

logger = structlog.get_logger(__name__)

LIST_LIMIT = 50
APPOINTMENTS_LINK = "/portal/appointments"
MEDICINES_LINK = "/portal/medicines"


def prescription_link(prescription_id: UUID) -> str:
    return f"/portal/prescriptions/{prescription_id}"


def linked_account(tenant: TenantRepositories, patient_id: UUID) -> UUID | None:
    """R56: the account actively linked to this record, if any."""
    link = tenant.portal_links.active_for_patient(patient_id)
    return link.account_id if link is not None else None


def patient_email_key(account_id: UUID, event_key: str) -> str:
    return f"patient_email:{account_id}:{event_key}"


def notify_patient(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    *,
    ids: IdPort,
    account_id: UUID,
    kind: PatientNotificationKind,
    event_key: str,
    entity: tuple[str, UUID],
    link: str,
    params: Mapping[str, str],
    now: datetime,
    request_id: str | None = None,
) -> int:
    """Deliver one notice to one account in the caller's transaction; returns the rows written."""
    written = 0
    if not uow.patient_preferences.is_off(account_id, kind, PatientChannel.IN_APP):
        written = len(
            tenant.patient_notifications.add_many(
                [
                    PatientNotification.create(
                        id=ids.new_id(),
                        clinic_id=tenant.clinic_id,
                        account_id=account_id,
                        kind=kind,
                        event_key=event_key,
                        entity=entity,
                        link=link,
                        params=params,
                        now=now,
                    )
                ]
            )
        )
    if kind in BOOKING_KINDS and not uow.patient_preferences.is_off(
        account_id, kind, PatientChannel.EMAIL
    ):
        account = uow.patient_accounts.get(account_id)
        if account is not None and account.is_email_verified:
            uow.jobs.enqueue(
                NewJob.create(
                    id=ids.new_id(),
                    kind=PATIENT_EMAIL_KIND,
                    now=now,
                    clinic_id=tenant.clinic_id,
                    payload={
                        "account_id": str(account_id),
                        "kind": kind.value,
                        "entity_id": str(entity[1]),
                    },
                    request_id=request_id,
                    dedupe_key=patient_email_key(account_id, event_key),
                )
            )
    logger.info("patient_notification.dispatched", kind=kind.value, written=written)
    return written


# --- The bell (R67, R68) ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NoticeView:
    id: UUID
    kind: PatientNotificationKind
    title: str
    link: str
    clinic_id: UUID
    created_at: datetime
    read_at: datetime | None


@dataclass(frozen=True, slots=True)
class NoticeSummary:
    unread: int
    latest_id: UUID | None


def _linked(uow: UnitOfWork, account_id: UUID) -> list[UUID]:
    return [entry.clinic.id for entry in PortalScope.read(uow, account_id)]


def render(
    uow: UnitOfWork, notices: Sequence[PatientNotification], lang: Language
) -> list[NoticeView]:
    clinics: dict[UUID, tuple[str, str]] = {}
    doctors: dict[tuple[UUID, str], str | None] = {}
    views = []
    for n in notices:
        if n.clinic_id not in clinics:
            clinic = uow.clinics.get(n.clinic_id)
            clinics[n.clinic_id] = (
                (clinic.name, clinic.timezone) if clinic is not None else ("", "Asia/Kolkata")
            )
        name, zone = clinics[n.clinic_id]
        doctor_id = n.params.get("doctor_id")
        doctor: str | None = None
        if doctor_id is not None:
            key = (n.clinic_id, doctor_id)
            if key not in doctors:
                found = uow.tenant(n.clinic_id).doctors.get(UUID(doctor_id))
                doctors[key] = found.display_name if found is not None else None
            doctor = doctors[key]
        views.append(
            NoticeView(
                id=n.id,
                kind=n.kind,
                title=render_title(n, Names(name, doctor, zone), lang),
                link=n.link,
                clinic_id=n.clinic_id,
                created_at=n.created_at,
                read_at=n.read_at,
            )
        )
    return views


class ListPatientNotifications:
    """``GET /portal/notifications``: the newest 50, titles in the account's language."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, principal: PatientPrincipal) -> list[NoticeView]:
        with self._uow as uow:
            linked = _linked(uow, principal.account_id)
            notices = uow.patient_notification_lookup.list_for(
                principal.account_id, linked, limit=LIST_LIMIT
            )
            return render(uow, notices, principal.account.language)


class GetPatientNotificationSummary:
    """``GET /portal/notifications/summary`` (R67): the bell's count, behind an ETag."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, principal: PatientPrincipal) -> NoticeSummary:
        with self._uow as uow:
            linked = _linked(uow, principal.account_id)
            lookup = uow.patient_notification_lookup
            latest = lookup.list_for(principal.account_id, linked, limit=1)
            return NoticeSummary(
                unread=lookup.unread_count(principal.account_id, linked),
                latest_id=latest[0].id if latest else None,
            )


class MarkPatientNotificationRead:
    """``POST /portal/notifications/{id}/read``; another account's (or a hidden) ID is 404."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, principal: PatientPrincipal, notification_id: UUID) -> None:
        with self._uow as uow:
            linked = _linked(uow, principal.account_id)
            lookup = uow.patient_notification_lookup
            if lookup.get_for(principal.account_id, linked, notification_id) is None:
                raise NotFound("notification")
            lookup.mark_read(principal.account_id, notification_id, self._clock.now())
            uow.commit()


class MarkAllPatientNotificationsRead:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, principal: PatientPrincipal) -> int:
        with self._uow as uow:
            linked = _linked(uow, principal.account_id)
            marked = uow.patient_notification_lookup.mark_all_read(
                principal.account_id, linked, self._clock.now()
            )
            uow.commit()
        return marked


@dataclass(frozen=True, slots=True)
class PreferenceView:
    kind: PatientNotificationKind
    in_app: bool
    email: bool | None  # None: email is not offered for this kind


class GetPatientPreferences:
    """R62, R63: every kind with its in-app switch, and the email switch for booking kinds."""

    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, principal: PatientPrincipal) -> list[PreferenceView]:
        with self._uow as uow:
            saved = {
                (p.kind, p.channel): p.enabled
                for p in uow.patient_preferences.list_for(principal.account_id)
            }
        return [
            PreferenceView(
                kind=kind,
                in_app=saved.get((kind, PatientChannel.IN_APP), True),
                email=saved.get((kind, PatientChannel.EMAIL), True)
                if kind in BOOKING_KINDS
                else None,
            )
            for kind in PatientNotificationKind
        ]


class SetPatientPreference:
    def __init__(self, *, uow: UnitOfWork, clock: ClockPort, ids: IdPort) -> None:
        self._uow = uow
        self._clock = clock
        self._ids = ids

    def execute(
        self,
        principal: PatientPrincipal,
        kind: PatientNotificationKind,
        channel: PatientChannel,
        enabled: bool,
    ) -> None:
        check_channel(kind, channel)
        with self._uow as uow:
            uow.patient_preferences.set(
                principal.account_id,
                PatientPreference(kind, channel, enabled),
                id=self._ids.new_id(),
                now=self._clock.now(),
            )
            uow.commit()
        logger.info(
            "patient_notification.preference_changed", kind=kind.value, channel=channel.value
        )
