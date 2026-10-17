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

from mediease_api.adapters.db.models import Base
from mediease_api.adapters.db.repositories import (
    SqlAlchemyAppointmentHistoryRepository,
    SqlAlchemyAppointmentRepository,
    SqlAlchemyChecklistRepository,
    SqlAlchemyDoctorRepository,
    SqlAlchemyMembershipRepository,
    SqlAlchemyPatientRepository,
    SqlAlchemyScheduleExceptionRepository,
    SqlAlchemyScheduleRepository,
    SqlAlchemySessionRepository,
)
from mediease_api.adapters.db.tenancy import TenancyViolation, TenantScopedRepository
from mediease_api.domain.appointments.appointment import Appointment, history_entry
from mediease_api.domain.clinics.doctor import Doctor
from mediease_api.domain.identity.membership import ClinicMembership, Role
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock
from mediease_api.domain.scheduling.exceptions import ScheduleException
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import Session, SessionStatus, plan_day
from mediease_api.domain.shared.errors import NotFound
from mediease_api.domain.shared.phone import PhoneNumber
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
NOT_TENANT_SCOPED = {"audit_events"}


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
            "audit_events",
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
    } == set(TenantScopedRepository.__subclasses__())


def _fields(entity: object) -> dict[str, object]:
    return {name: getattr(entity, name) for name in entity.__slots__}  # type: ignore[attr-defined]
