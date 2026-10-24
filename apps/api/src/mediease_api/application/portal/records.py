"""What a linked patient account reads (M6b-P1; FR-PRT-03, NFR-18; spec R9-R13, decision 4A).

Read only, and only through ``PortalScope``: for each active link, that one clinic and that one
patient record. Returned: the clinic's contact details, the record's appointments (every status),
issued prescriptions (the latest version per chain: the patient page and its PDF) and reminders
with their visible status. **Never** visit notes, vitals, diagnosis, drafts, addenda, an
appointment's reason or a staff note. Reads are not audited (decision 7A).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

import structlog

from mediease_api.application.portal.linking import first_name
from mediease_api.application.portal.scope import PortalScope, ScopeEntry
from mediease_api.application.portal.views import PatientPrincipal
from mediease_api.application.prescriptions.pdf import DownloadPrescriptionPdf, PdfDownload
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.link import LinkMethod
from mediease_api.domain.prescriptions.patient_view import PatientPage, build_patient_view
from mediease_api.domain.prescriptions.prescription import Prescription, PrescriptionStatus
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.domain.shared.errors import NotFound
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)

APPOINTMENTS_PER_CLINIC = 50
PRESCRIPTIONS_PER_CLINIC = 50
REMINDERS_PER_CLINIC = 50


@dataclass(frozen=True, slots=True)
class PortalLinkView:
    """R10: one linked clinic and the record's first name and code."""

    link_id: UUID
    clinic_id: UUID
    clinic_name: str
    clinic_phone_e164: str | None
    clinic_address_line: str | None
    clinic_city: str | None
    # M6b-P2 (spec R22): times are shown on the clinic's clock.
    clinic_timezone: str
    patient_first_name: str
    patient_code: str
    method: LinkMethod
    linked_at: datetime


@dataclass(frozen=True, slots=True)
class PortalAppointment:
    """R11: no reason, no notes, no staff fields."""

    appointment: Appointment
    session: Session
    doctor_name: str

    @property
    def starts_at(self) -> datetime:
        return self.appointment.slot_start or self.session.starts_at


@dataclass(frozen=True, slots=True)
class PortalAppointmentGroup:
    clinic_id: UUID
    clinic_name: str
    clinic_timezone: str
    clinic_phone_e164: str | None
    appointments: list[PortalAppointment]


@dataclass(frozen=True, slots=True)
class PortalPrescription:
    """R12: the chain's latest issued version, without content."""

    id: UUID
    clinic_id: UUID
    clinic_name: str
    doctor_name: str
    version: int
    issued_at: datetime


@dataclass(frozen=True, slots=True)
class PortalReminder:
    """R13 (FR-REM-05): kind, date, due time and the visible status."""

    id: UUID
    clinic_id: UUID
    clinic_name: str
    kind: str
    follow_up_date: date
    due_at: datetime
    status: str


class _Reads:
    def __init__(self, *, uow: UnitOfWork) -> None:
        self._uow = uow


class ListPortalLinks(_Reads):
    def execute(self, principal: PatientPrincipal) -> list[PortalLinkView]:
        with self._uow as uow:
            return [
                PortalLinkView(
                    link_id=e.link.id,
                    clinic_id=e.clinic.id,
                    clinic_name=e.clinic.name,
                    clinic_phone_e164=e.clinic.phone.e164 if e.clinic.phone else None,
                    clinic_address_line=e.clinic.address_line,
                    clinic_city=e.clinic.city,
                    clinic_timezone=e.clinic.timezone,
                    patient_first_name=first_name(e.patient),
                    patient_code=e.patient.code,
                    method=e.link.method,
                    linked_at=e.link.created_at,
                )
                for e in PortalScope.read(uow, principal.account_id)
            ]


class ListPortalAppointments:
    """R11: grouped by clinic; upcoming first (soonest first), then past (newest first)."""

    def __init__(self, *, uow: UnitOfWork, clock: ClockPort) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, principal: PatientPrincipal) -> list[PortalAppointmentGroup]:
        now = self._clock.now()
        with self._uow as uow:
            groups = [
                PortalAppointmentGroup(
                    e.clinic.id,
                    e.clinic.name,
                    e.clinic.timezone,
                    e.clinic.phone.e164 if e.clinic.phone else None,
                    self._for(e, now),
                )
                for e in PortalScope.read(uow, principal.account_id)
            ]
        return groups

    @staticmethod
    def _for(entry: ScopeEntry, now: datetime) -> list[PortalAppointment]:
        tenant = entry.tenant
        appointments = tenant.appointments.list_for_patient(
            entry.patient_id, limit=APPOINTMENTS_PER_CLINIC
        )
        sessions = {s.id: s for s in tenant.sessions.get_many({a.session_id for a in appointments})}
        doctors = {d.id: d.display_name for d in tenant.doctors.list()}
        rows = [
            PortalAppointment(a, sessions[a.session_id], doctors.get(a.doctor_id, ""))
            for a in appointments
        ]
        upcoming = sorted((r for r in rows if r.session.ends_at > now), key=lambda r: r.starts_at)
        past = sorted(
            (r for r in rows if r.session.ends_at <= now), key=lambda r: r.starts_at, reverse=True
        )
        return upcoming + past


class ListPortalPrescriptions(_Reads):
    """R12: every linked record's current versions, newest issue first."""

    def execute(self, principal: PatientPrincipal) -> list[PortalPrescription]:
        items = []
        with self._uow as uow:
            for e in PortalScope.read(uow, principal.account_id):
                for rx in e.tenant.prescriptions.list_issued_for_patient(
                    e.patient_id, limit=PRESCRIPTIONS_PER_CLINIC
                ):
                    assert rx.issued_at is not None and rx.doctor_snapshot is not None
                    items.append(
                        PortalPrescription(
                            id=rx.id,
                            clinic_id=e.clinic.id,
                            clinic_name=e.clinic.name,
                            doctor_name=rx.doctor_snapshot.display_name,
                            version=rx.version,
                            issued_at=rx.issued_at,
                        )
                    )
        return sorted(items, key=lambda p: p.issued_at, reverse=True)


def issued_in_scope(scope: PortalScope, rx_id: UUID) -> tuple[ScopeEntry, Prescription]:
    """R9, R12: a current (``ISSUED``) version of a linked record; anything else is not found."""
    for entry in scope:
        rx = entry.tenant.prescriptions.get(rx_id)
        if rx is not None and rx.patient_id == entry.patient_id:
            if rx.status is PrescriptionStatus.ISSUED:
                return entry, rx
            break
    logger.info("portal.not_found", entity="prescription", entity_id=str(rx_id))
    raise NotFound("prescription")


class GetPortalPrescription(_Reads):
    """The patient page, as the prescription link shows it (``?lang=en|hi``; else the account's
    language, M6b-P2 decision 2A)."""

    def execute(
        self, principal: PatientPrincipal, rx_id: UUID, language: Language | None
    ) -> PatientPage:
        with self._uow as uow:
            entry, rx = issued_in_scope(PortalScope.read(uow, principal.account_id), rx_id)
            chain = list(entry.tenant.prescriptions.list_for_visit(rx.visit_id))
        page = build_patient_view(
            chain, language=language or principal.account.language, timezone=entry.clinic.timezone
        )
        assert page is not None  # the chain has an issued version: rx
        return page


class PortalPrescriptionPdf:
    """The version's PDF, rendered once and shared with the clinic's (prescriptions R18)."""

    def __init__(self, *, uow: UnitOfWork, pdf: DownloadPrescriptionPdf) -> None:
        self._uow = uow
        self._pdf = pdf

    def execute(self, principal: PatientPrincipal, rx_id: UUID) -> PdfDownload:
        with self._uow as uow:
            entry, rx = issued_in_scope(PortalScope.read(uow, principal.account_id), rx_id)
            rx, data, rendered = self._pdf.file_for(uow, entry.tenant, rx)
            uow.commit()
        return PdfDownload(rx.id, rx.version, data, rendered)


class ListPortalReminders(_Reads):
    """R13: each linked record's reminders, soonest due first."""

    def execute(self, principal: PatientPrincipal) -> list[PortalReminder]:
        items = []
        with self._uow as uow:
            for e in PortalScope.read(uow, principal.account_id):
                for read in e.tenant.reminders.list_for_patient(
                    e.patient_id, limit=REMINDERS_PER_CLINIC
                ):
                    r = read.reminder
                    items.append(
                        PortalReminder(
                            id=r.id,
                            clinic_id=e.clinic.id,
                            clinic_name=e.clinic.name,
                            kind=r.kind.value,
                            follow_up_date=r.follow_up_date,
                            due_at=r.due_at,
                            status=read.visible_status,
                        )
                    )
        return sorted(items, key=lambda r: r.due_at)
