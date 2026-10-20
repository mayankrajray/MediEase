"""Tenancy isolation at the repository layer (NFR-08, ADR-0003, spec R8).

Permanent suite: two clinics, A and B, each with doctors and memberships.
Repositories bound to clinic A must behave as if clinic B's rows do not
exist — for reads, lists, counts and writes — and must refuse an entity that
belongs to B. From M1-P3 the same isolation is proved again at the HTTP level.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from uuid import UUID, uuid4

import pytest

from mediease_api.adapters.db.messages import SqlAlchemyMessageRepository
from mediease_api.adapters.db.models import Base
from mediease_api.adapters.db.reminders import SqlAlchemyReminderRepository
from mediease_api.adapters.db.repositories import (
    SqlAlchemyAppointmentHistoryRepository,
    SqlAlchemyAppointmentRepository,
    SqlAlchemyChecklistRepository,
    SqlAlchemyDoctorRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyPatientLinkRepository,
    SqlAlchemyPatientRepository,
    SqlAlchemyPrescriptionItemRepository,
    SqlAlchemyPrescriptionRepository,
    SqlAlchemyRxFavouriteRepository,
    SqlAlchemyRxTemplateRepository,
    SqlAlchemyScheduleExceptionRepository,
    SqlAlchemyScheduleRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyVisitAddendumRepository,
    SqlAlchemyVisitRepository,
)
from mediease_api.adapters.db.tenancy import TenancyViolation, TenantScopedRepository
from mediease_api.domain.appointments.appointment import Appointment, history_entry
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import ClinicMembership, Role
from mediease_api.domain.links.link import PatientLink
from mediease_api.domain.messaging.message import Channel, Message, SourceType
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.prescriptions.library import Favourite, Template
from mediease_api.domain.prescriptions.prescription import Advice, Prescription, PrescriptionItem
from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock
from mediease_api.domain.scheduling.exceptions import ScheduleException
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session, SessionStatus, plan_day
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
from mediease_api.domain.visits.visit import Visit, VisitStatus
from mediease_api.domain.visits.vitals import Vitals
from mediease_api.ports.repositories import RowLock
from tests.builders import LATER, NOW, a_clinic, a_doctor, a_membership, a_patient, a_user, new_id
from tests.conftest import UowFactory


@dataclass(frozen=True)
class Tenant:
    clinic_id: UUID
    doctor: Doctor
    owner: ClinicMembership
    patient: Patient


# Reviewed exception (M1-P4): audit_events carries clinic_id but is deliberately
# not reachable through a tenant repository. It is append-only, written only by
# the audit writer with the clinic ID from the request context, and it also holds
# platform-level rows (clinic_id null for a sign-in). Nothing in the application
# reads it; an owner-facing read (FR-AUD-03) must scope its own query by clinic
# and add cases to this suite.
#
# Reviewed exception (M5-P1): jobs carries a nullable clinic_id on purpose. It is null exactly for
# the system kinds a CHECK lists (the retention purge), so no tenant repository can own the table.
# Only the job queue (enqueue, in the unit of work) and the worker's store touch it; the store never
# reads a clinic's rows, and a job's handler is given that job's clinic only
# (tests/integration/test_jobs_db.py).
#
# Reviewed exception (M5-P3): SqlAlchemyMessageLookup reads messages across clinics, because a
# provider webhook names no clinic. It returns only the clinic and message IDs; the message is then
# read and changed through that clinic's SqlAlchemyMessageRepository
# (tests/integration/test_webhooks_http.py). webhook_events has no clinic_id.
#
# Reviewed exception (M5-P4): SqlAlchemyNoShowSweep returns the IDs of active clinics with bookings
# overdue for NO_SHOW; each clinic's own mark_no_shows job then reads and changes only its rows
# through the tenant repositories (tests/integration/test_reminders_http.py).
#
# Reviewed exception (M5-P5): SqlAlchemyOptOutLookup matches a STOP reply's number across clinics,
# because a reply names no clinic. It returns only clinic and patient IDs (patients with that
# number in clinics that have messaged it); each patient is then locked, opted out and audited
# through that clinic's SqlAlchemyPatientRepository (tests/integration/test_opt_out_db.py).
#
# Reviewed exception (M5-P5): SqlAlchemyMessageCostReport sums messages across clinics for the ops
# console's monthly total (decision 7A), like the ops clinic list. It returns counts and sums per
# clinic and channel only, never a message, patient or number, and only ops reach it
# (tests/integration/test_message_costs_db.py).
NOT_TENANT_SCOPED = {"audit_events", "jobs"}


@pytest.fixture
def two_clinics(uow_factory: UowFactory) -> tuple[Tenant, Tenant]:
    """Clinics A and B, each with one doctor and one active owner."""
    tenants = []
    with uow_factory() as uow:
        for _ in range(2):
            clinic, owner = a_clinic(), a_user()
            uow.clinics.add(clinic)
            uow.users.add(owner)
            staff = uow.tenant(clinic.id)
            doctor = a_doctor(clinic.id, user_id=owner.id)
            membership = a_membership(clinic.id, owner.id, Role.OWNER)
            staff.doctors.add(doctor)
            staff.memberships.add(membership)
            # Both clinics hold a patient with the same phone and a similar name on purpose.
            patient = a_patient(
                clinic.id, owner.id, full_name="Asha Rao", phone=PhoneNumber.parse("9000000001")
            )
            staff.patients.add(patient)
            tenants.append(Tenant(clinic.id, doctor, membership, patient))
        uow.commit()
    return tenants[0], tenants[1]


def test_nfr_08_clinic_a_cannot_read_clinic_b_doctors(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    with uow_factory() as uow:
        doctors = uow.tenant(a.clinic_id).doctors
        assert doctors.get(b.doctor.id) is None
        assert doctors.get(a.doctor.id) == a.doctor
        assert [d.id for d in doctors.list()] == [a.doctor.id]


def test_nfr_08_clinic_a_cannot_read_clinic_b_memberships(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    with uow_factory() as uow:
        memberships = uow.tenant(a.clinic_id).memberships
        assert memberships.get(b.owner.id) is None
        assert memberships.get_for_user(b.owner.user_id) is None
        assert [m.id for m in memberships.list()] == [a.owner.id]
        assert memberships.count_active_owners() == 1


def test_nfr_08_ac7_clinic_a_cannot_find_clinic_b_patients_by_any_route(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    shared_phone = PhoneNumber.parse("9000000001")
    with uow_factory() as uow:
        patients = uow.tenant(a.clinic_id).patients
        assert patients.get(b.patient.id) is None
        assert patients.get(a.patient.id) == a.patient
        assert patients.get_by_code(b.patient.code) is None
        # Same phone and same name in both clinics: only A's patient comes back.
        assert [p.id for p in patients.find_by_phone(shared_phone, limit=10)] == [a.patient.id]
        assert [p.id for p in patients.find_by_phones([shared_phone])] == [a.patient.id]
        assert [p.id for p in patients.search_by_name_prefix("asha", limit=20)] == [a.patient.id]
        assert patients.count() == 1


def test_nfr_08_identity_map_does_not_leak_across_scopes(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    # Clinic B's rows are already loaded in this session; A's scope still hides them.
    a, b = two_clinics
    with uow_factory() as uow:
        assert uow.tenant(b.clinic_id).doctors.get(b.doctor.id) is not None
        assert uow.tenant(b.clinic_id).memberships.get(b.owner.id) is not None
        assert uow.tenant(b.clinic_id).patients.get(b.patient.id) is not None
        assert uow.tenant(a.clinic_id).patients.get(b.patient.id) is None
        assert uow.tenant(a.clinic_id).doctors.get(b.doctor.id) is None
        assert uow.tenant(a.clinic_id).memberships.get(b.owner.id) is None


def test_r8_clinic_a_cannot_update_clinic_b_rows(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    with uow_factory() as uow:
        staff_a = uow.tenant(a.clinic_id)
        # An entity forged with A's clinic_id but B's row ID is simply not found.
        forged_doctor = Doctor(**{**_fields(b.doctor), "clinic_id": a.clinic_id})
        with pytest.raises(NotFound) as excinfo:
            staff_a.doctors.update(forged_doctor)
        assert excinfo.value.details == {"entity": "doctor"}

        forged_membership = ClinicMembership(**{**_fields(b.owner), "clinic_id": a.clinic_id})
        forged_membership.deactivate(active_owner_count=2, now=LATER)
        with pytest.raises(NotFound):
            staff_a.memberships.update(forged_membership)

        forged_patient = Patient(**{**_fields(b.patient), "clinic_id": a.clinic_id})
        forged_patient.update_details(today=date(2026, 10, 3), now=LATER, full_name="Hijacked")
        with pytest.raises(NotFound) as excinfo_patient:
            staff_a.patients.update(forged_patient)
        assert excinfo_patient.value.details == {"entity": "patient"}
        uow.commit()

    with uow_factory() as uow:
        assert uow.tenant(b.clinic_id).doctors.get(b.doctor.id) == b.doctor
        assert uow.tenant(b.clinic_id).memberships.get(b.owner.id) == b.owner
        assert uow.tenant(b.clinic_id).patients.get(b.patient.id) == b.patient


def test_repositories_refuse_entities_of_another_clinic(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    with uow_factory() as uow:
        staff_a = uow.tenant(a.clinic_id)
        with pytest.raises(TenancyViolation):
            staff_a.doctors.add(a_doctor(b.clinic_id))
        with pytest.raises(TenancyViolation):
            staff_a.doctors.update(b.doctor)
        with pytest.raises(TenancyViolation):
            staff_a.memberships.add(a_membership(b.clinic_id, b.owner.user_id))
        with pytest.raises(TenancyViolation):
            staff_a.memberships.update(b.owner)
        with pytest.raises(TenancyViolation):
            staff_a.patients.add(a_patient(b.clinic_id, b.owner.user_id))
        with pytest.raises(TenancyViolation):
            staff_a.patients.update(b.patient)


def test_unknown_clinic_scope_sees_nothing(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    with uow_factory() as uow:
        staff = uow.tenant(uuid4())
        assert staff.doctors.list() == []
        assert staff.memberships.list() == []
        assert staff.memberships.count_active_owners() == 0
        assert staff.patients.count() == 0
        assert staff.patients.search_by_name_prefix("a", limit=20) == []


def test_nfr_08_clinic_a_cannot_reach_clinic_b_schedules_exceptions_or_sessions(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    day = date(2026, 10, 19)  # a Monday
    shape = BlockShape(time(10), time(13), 15, 12)
    with uow_factory() as uow:
        staff_b = uow.tenant(b.clinic_id)
        block = WeeklyBlock.create(
            id=new_id(),
            clinic_id=b.clinic_id,
            doctor_id=b.doctor.id,
            weekday=0,
            shape=shape,
            mode=BookingMode.TOKENS,
            valid_from=day,
            now=NOW,
        )
        staff_b.schedules.add(block)
        leave = ScheduleException.leave(
            id=new_id(), clinic_id=b.clinic_id, doctor_id=b.doctor.id, on_date=day, now=NOW
        )
        staff_b.schedule_exceptions.add(leave)
        plan = plan_day(
            doctor_id=b.doctor.id,
            on_date=day,
            timezone="Asia/Kolkata",
            mode=BookingMode.TOKENS,
            blocks=[block],
            exceptions=[],
        )
        session = Session.from_plan(plan[0], id=new_id(), clinic_id=b.clinic_id, now=NOW)
        assert staff_b.sessions.add_missing([session]) == 1
        uow.commit()

    with uow_factory() as uow:
        staff_a = uow.tenant(a.clinic_id)
        # Asking A's scope about B's doctor finds nothing of B's.
        assert staff_a.schedules.list_for_doctor(b.doctor.id, valid_since=day) == []
        assert staff_a.schedules.list_current(valid_since=day) == []
        assert staff_a.schedule_exceptions.get(leave.id) is None
        assert staff_a.schedule_exceptions.list_from(day) == []
        assert staff_a.schedule_exceptions.list_for_doctor(b.doctor.id, first=day, last=day) == []
        assert staff_a.sessions.list_for_date(day) == []
        assert staff_a.sessions.list_for_doctor(b.doctor.id, first=day) == []
        with pytest.raises(NotFound):
            staff_a.schedules.delete(block.id)
        with pytest.raises(NotFound):
            staff_a.schedule_exceptions.delete(leave.id)
        with pytest.raises(NotFound):
            staff_a.sessions.delete(session.id)
        with pytest.raises(TenancyViolation):
            staff_a.schedules.add(block)
        with pytest.raises(TenancyViolation):
            staff_a.schedules.update(block)
        with pytest.raises(TenancyViolation):
            staff_a.schedule_exceptions.add(leave)
        with pytest.raises(TenancyViolation):
            staff_a.sessions.add_missing([session])
        uow.commit()

    with uow_factory() as uow:
        staff_b = uow.tenant(b.clinic_id)
        assert [s.id for s in staff_b.sessions.list_for_date(day)] == [session.id]
        assert staff_b.schedule_exceptions.get(leave.id) == leave


def test_nfr_08_clinic_a_cannot_reach_clinic_b_appointments_or_their_history(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    day = date(2026, 10, 19)
    with uow_factory() as uow:
        staff_b = uow.tenant(b.clinic_id)
        [planned] = plan_day(
            doctor_id=b.doctor.id,
            on_date=day,
            timezone="Asia/Kolkata",
            mode=BookingMode.TOKENS,
            blocks=[
                WeeklyBlock.create(
                    id=new_id(),
                    clinic_id=b.clinic_id,
                    doctor_id=b.doctor.id,
                    weekday=0,
                    shape=BlockShape(time(10), time(13), 15, 12),
                    mode=BookingMode.TOKENS,
                    valid_from=day,
                    now=NOW,
                )
            ],
            exceptions=[],
        )
        session = Session.from_plan(planned, id=new_id(), clinic_id=b.clinic_id, now=NOW)
        staff_b.sessions.add_missing([session])
        appointment = Appointment.book(
            session, id=new_id(), patient_id=b.patient.id, active=[], now=NOW
        )
        staff_b.sessions.update(session)
        staff_b.appointments.add(appointment)
        staff_b.appointment_history.add(
            history_entry(
                appointment, id=new_id(), from_status=None, changed_by=None, request_id=None
            )
        )
        uow.commit()

    with uow_factory() as uow:
        staff_a = uow.tenant(a.clinic_id)
        assert staff_a.sessions.get(session.id) is None
        assert staff_a.sessions.get_many([session.id]) == []
        assert staff_a.appointments.get(appointment.id) is None
        assert staff_a.appointments.get(appointment.id, for_update=True) is None
        assert staff_a.appointments.list_active_for_sessions([session.id]) == []
        assert staff_a.appointments.list_for_sessions([session.id]) == []
        assert staff_a.patients.get_many([b.patient.id]) == []
        assert not staff_a.appointments.exists_for_session(session.id)
        assert staff_a.appointments.list_for_patient(b.patient.id, limit=10) == []
        assert staff_a.appointment_history.list_for_appointment(appointment.id) == []
        with pytest.raises(TenancyViolation):
            staff_a.sessions.update(session)
        with pytest.raises(TenancyViolation):
            staff_a.appointments.add(appointment)
        with pytest.raises(TenancyViolation):
            staff_a.appointments.update(appointment)
        with pytest.raises(TenancyViolation):
            staff_a.appointment_history.add(
                history_entry(
                    appointment, id=new_id(), from_status=None, changed_by=None, request_id=None
                )
            )

    with uow_factory() as uow:
        staff_b = uow.tenant(b.clinic_id)
        stored = staff_b.appointments.get(appointment.id)
        assert stored == appointment and stored.token_number == 1
        assert staff_b.appointments.exists_for_session(session.id)
        assert [
            h.appointment_id
            for h in staff_b.appointment_history.list_for_appointment(appointment.id)
        ] == [appointment.id]
        locked = staff_b.sessions.get(session.id, lock=RowLock.UPDATE)
        assert locked is not None and locked.booked_count == 1 and locked.next_token == 2
        locked.booked_count = 0
        locked.retire(LATER)
        staff_b.sessions.update(locked)
        assert staff_b.sessions.list_for_date(day) == []
        assert [s.status for s in staff_b.sessions.list_for_date(day, include_retired=True)] == [
            SessionStatus.CANCELLED
        ]


def test_nfr_08_clinic_a_cannot_reach_clinic_b_visits_or_addenda(
    uow_factory: UowFactory, two_clinics: tuple[Tenant, Tenant]
) -> None:
    a, b = two_clinics
    day = date(2026, 10, 19)
    with uow_factory() as uow:
        staff_b = uow.tenant(b.clinic_id)
        [planned] = plan_day(
            doctor_id=b.doctor.id,
            on_date=day,
            timezone="Asia/Kolkata",
            mode=BookingMode.TOKENS,
            blocks=[
                WeeklyBlock.create(
                    id=new_id(),
                    clinic_id=b.clinic_id,
                    doctor_id=b.doctor.id,
                    weekday=0,
                    shape=BlockShape(time(10), time(13), 15, 12),
                    mode=BookingMode.TOKENS,
                    valid_from=day,
                    now=NOW,
                )
            ],
            exceptions=[],
        )
        session = Session.from_plan(planned, id=new_id(), clinic_id=b.clinic_id, now=NOW)
        staff_b.sessions.add_missing([session])
        appointment = Appointment.book(
            session, id=new_id(), patient_id=b.patient.id, active=[], now=NOW
        )
        staff_b.sessions.update(session)
        staff_b.appointments.add(appointment)
        visit = Visit(
            id=new_id(),
            clinic_id=b.clinic_id,
            patient_id=b.patient.id,
            doctor_id=b.doctor.id,
            appointment_id=appointment.id,
            status=VisitStatus.OPEN,
            chief_complaint="cough",
            findings=None,
            diagnosis=None,
            notes=None,
            vitals=Vitals.parse({"pulse": 80}),
            revision=1,
            started_at=NOW,
            completed_at=None,
            locked_at=None,
            created_by=b.owner.user_id,
            created_at=NOW,
            updated_at=NOW,
        )
        staff_b.visits.add(visit)
        visit.complete(NOW)
        staff_b.visits.update(visit)
        addendum = visit.addendum(
            id=new_id(), author_user_id=b.owner.user_id, body="seen again", now=LATER
        )
        staff_b.visit_addenda.add(addendum)
        rx = Prescription.first_draft(visit, id=new_id(), created_by=b.owner.user_id, now=NOW)
        rx.replace_body(
            items=[PrescriptionItem.create(id=new_id(), position=1, medicine_name="Tab Y")],
            advice=Advice(),
            follow_up_date=None,
            seen_revision=1,
            today=NOW.date(),
            now=NOW,
        )
        staff_b.prescriptions.add(rx)
        fav = Favourite.create(
            id=new_id(),
            clinic_id=b.clinic_id,
            doctor_id=b.doctor.id,
            name="Tab Y usual",
            item=rx.items[0],
            now=NOW,
        )
        staff_b.rx_favourites.add(fav)
        template = Template.create(
            id=new_id(),
            clinic_id=b.clinic_id,
            doctor_id=b.doctor.id,
            name="Cough",
            items=list(rx.items),
            advice=Advice(),
            follow_up_days=None,
            now=NOW,
        )
        staff_b.rx_templates.add(template)
        link = PatientLink.create(
            id=new_id(),
            clinic_id=b.clinic_id,
            patient_id=b.patient.id,
            prescription_id=rx.id,
            key_id="k1",
            ttl_days=90,
            created_by=b.owner.user_id,
            now=NOW,
        )
        staff_b.patient_links.add(link)
        message = _a_message(b, appointment.id)
        staff_b.messages.add(message)
        uow.commit()

    with uow_factory() as uow:
        staff_a = uow.tenant(a.clinic_id)
        assert staff_a.visits.get(visit.id) is None
        assert staff_a.visits.get(visit.id, for_update=True) is None
        assert staff_a.visits.get_for_appointment(appointment.id) is None
        assert staff_a.visits.list_for_patient(b.patient.id, limit=10) == []
        assert staff_a.visit_addenda.list_for_visit(visit.id) == []
        with pytest.raises(TenancyViolation):
            staff_a.visits.add(visit)
        with pytest.raises(TenancyViolation):
            staff_a.visits.update(visit)
        with pytest.raises(TenancyViolation):
            staff_a.visit_addenda.add(addendum)
        assert staff_a.prescriptions.get(rx.id) is None
        assert staff_a.prescriptions.get(rx.id, for_update=True) is None
        assert staff_a.prescriptions.list_for_visits([visit.id]) == []
        with pytest.raises(TenancyViolation):
            staff_a.prescriptions.add(rx)
        with pytest.raises(TenancyViolation):
            staff_a.prescriptions.update(rx)
        with pytest.raises(TenancyViolation):
            staff_a.prescriptions.replace_items(rx)
        with pytest.raises(NotFound):
            staff_a.prescriptions.delete(rx.id)
        assert staff_a.rx_favourites.get(fav.id) is None
        assert staff_a.rx_favourites.list_for_doctor(b.doctor.id) == []
        assert staff_a.rx_favourites.count_for_doctor(b.doctor.id) == 0
        assert staff_a.rx_templates.get(template.id) is None
        assert staff_a.rx_templates.list_for_doctor(b.doctor.id) == []
        assert staff_a.patient_links.get(link.id) is None
        assert staff_a.patient_links.get(link.id, for_update=True) is None
        assert staff_a.patient_links.active_for_prescription(rx.id) is None
        with pytest.raises(TenancyViolation):
            staff_a.patient_links.add(link)
        with pytest.raises(TenancyViolation):
            staff_a.patient_links.update(link)
        assert staff_a.messages.get_by_key(message.idempotency_key) is None
        assert staff_a.messages.get_by_key(message.idempotency_key, for_update=True) is None
        with pytest.raises(TenancyViolation):
            staff_a.messages.add(message)
        with pytest.raises(TenancyViolation):
            staff_a.messages.update(message)
        assert staff_a.prescriptions.medicine_history("tab", limit=10) == []
        with pytest.raises(TenancyViolation):
            staff_a.rx_favourites.add(fav)
        with pytest.raises(TenancyViolation):
            staff_a.rx_templates.update(template)
        with pytest.raises(NotFound):
            staff_a.rx_favourites.delete(fav.id)

    with uow_factory() as uow:
        staff_b = uow.tenant(b.clinic_id)
        assert staff_b.visits.get(visit.id) == visit
        assert staff_b.visits.get_for_appointment(appointment.id) == visit
        assert staff_b.visits.list_for_patient(b.patient.id, limit=10) == [visit]
        assert staff_b.visit_addenda.list_for_visit(visit.id) == [addendum]
        assert staff_b.prescriptions.get(rx.id) == rx
        assert staff_b.messages.get_by_key(message.idempotency_key) is not None
        assert staff_b.prescriptions.list_for_visit(visit.id) == [rx]
        assert [f.id for f in staff_b.rx_favourites.list_for_doctor(b.doctor.id)] == [fav.id]
        assert staff_b.rx_templates.get(template.id) is not None


def test_every_tenant_table_has_a_scoped_repository() -> None:
    """A new table with clinic_id must get a TenantScopedRepository (and tests here)."""
    tenant_tables = {
        table.name for table in Base.metadata.sorted_tables if "clinic_id" in table.columns
    }
    scoped_tables = {
        repo.model.__table__.name  # type: ignore[attr-defined]
        for repo in TenantScopedRepository.__subclasses__()
    }
    assert (
        tenant_tables
        == scoped_tables | NOT_TENANT_SCOPED
        == {
            "doctors",
            "clinic_memberships",
            "onboarding_checklists",
            "patients",
            "doctor_schedules",
            "schedule_exceptions",
            "sessions",
            "appointments",
            "appointment_status_history",
            "visits",
            "visit_addenda",
            "prescriptions",
            "prescription_items",
            "rx_favourites",
            "rx_templates",
            "patient_links",
            "messages",
            "reminders",
            "audit_events",
            "jobs",
        }
    )
    assert {
        SqlAlchemyChecklistRepository,
        SqlAlchemyDoctorRepository,
        SqlAlchemyMembershipRepository,
        SqlAlchemyPatientRepository,
        SqlAlchemyScheduleRepository,
        SqlAlchemyScheduleExceptionRepository,
        SqlAlchemySessionRepository,
        SqlAlchemyAppointmentRepository,
        SqlAlchemyAppointmentHistoryRepository,
        SqlAlchemyVisitRepository,
        SqlAlchemyVisitAddendumRepository,
        SqlAlchemyPrescriptionRepository,
        SqlAlchemyPrescriptionItemRepository,
        SqlAlchemyRxFavouriteRepository,
        SqlAlchemyRxTemplateRepository,
        SqlAlchemyPatientLinkRepository,
        SqlAlchemyMessageRepository,
        SqlAlchemyReminderRepository,
    } == set(TenantScopedRepository.__subclasses__())


def _a_message(tenant: Tenant, appointment_id: UUID) -> Message:
    return Message.prepare(
        id=new_id(),
        clinic_id=tenant.clinic_id,
        patient_id=tenant.patient.id,
        source_type=SourceType.APPOINTMENT,
        source_id=appointment_id,
        channel=Channel.CONSOLE,
        provider="console",
        template_key="booking_confirmed",
        template_version=1,
        language=tenant.patient.language,
        variables={"clinic_name": "Sample Clinic"},
        to_phone_encrypted="ciphertext",
        idempotency_key=f"booking_confirmed:{appointment_id}",
        request_id=None,
        job_id=None,
        now=NOW,
    )


def _fields(entity: object) -> dict[str, object]:
    return {name: getattr(entity, name) for name in entity.__slots__}  # type: ignore[attr-defined]
