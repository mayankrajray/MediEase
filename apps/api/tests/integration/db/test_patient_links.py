"""Patient links and public rate limits on PostgreSQL (M4-P5, migration 0013)."""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from mediease_api.domain.links.link import PatientLink
from mediease_api.domain.prescriptions.prescription import (
    Advice,
    Prescription,
    PrescriptionItem,
)
from mediease_api.domain.visits.visit import Visit, VisitStatus
from mediease_api.domain.visits.vitals import Vitals
from tests.builders import LATER, NOW, a_clinic, a_doctor, a_patient, a_user, new_id
from tests.conftest import UowFactory


def _chain(uow_factory: UowFactory) -> tuple[Prescription, object]:
    """A clinic, its doctor, patient, visit and a draft (the FK target is enough here)."""
    from mediease_api.domain.appointments.appointment import Appointment
    from mediease_api.domain.scheduling.blocks import BlockShape, WeeklyBlock
    from mediease_api.domain.scheduling.mode import BookingMode
    from mediease_api.domain.scheduling.sessions import Session, plan_day

    clinic, user = a_clinic(), a_user()
    doctor = a_doctor(clinic.id)
    patient = a_patient(clinic.id, user.id)
    with uow_factory() as uow:
        uow.clinics.add(clinic)
        uow.users.add(user)
        staff = uow.tenant(clinic.id)
        staff.doctors.add(doctor)
        staff.patients.add(patient)
        day = NOW.date()
        [planned] = plan_day(
            doctor_id=doctor.id,
            on_date=day,
            timezone="Asia/Kolkata",
            mode=BookingMode.TOKENS,
            blocks=[
                WeeklyBlock.create(
                    id=new_id(),
                    clinic_id=clinic.id,
                    doctor_id=doctor.id,
                    weekday=day.weekday(),
                    shape=BlockShape(time(9), time(13), 15, 12),
                    mode=BookingMode.TOKENS,
                    valid_from=day,
                    now=NOW,
                )
            ],
            exceptions=[],
        )
        session = Session.from_plan(planned, id=new_id(), clinic_id=clinic.id, now=NOW)
        staff.sessions.add_missing([session])
        appointment = Appointment.book(
            session, id=new_id(), patient_id=patient.id, active=[], now=NOW
        )
        staff.sessions.update(session)
        staff.appointments.add(appointment)
        visit = Visit(
            id=new_id(),
            clinic_id=clinic.id,
            patient_id=patient.id,
            doctor_id=doctor.id,
            appointment_id=appointment.id,
            status=VisitStatus.OPEN,
            chief_complaint=None,
            findings=None,
            diagnosis=None,
            notes=None,
            vitals=Vitals.empty(),
            revision=1,
            started_at=NOW,
            completed_at=None,
            locked_at=None,
            created_by=user.id,
            created_at=NOW,
            updated_at=NOW,
        )
        staff.visits.add(visit)
        rx = Prescription.first_draft(visit, id=new_id(), created_by=user.id, now=NOW)
        rx.replace_body(
            items=[PrescriptionItem.create(id=new_id(), position=1, medicine_name="Tab Y")],
            advice=Advice(),
            follow_up_date=None,
            seen_revision=1,
            today=NOW.date(),
            now=NOW,
        )
        staff.prescriptions.add(rx)
        uow.commit()
    return rx, user


def _link(rx: Prescription, user_id: object) -> PatientLink:
    return PatientLink.create(
        id=new_id(),
        clinic_id=rx.clinic_id,
        patient_id=rx.patient_id,
        prescription_id=rx.id,
        key_id="k1",
        ttl_days=90,
        created_by=user_id,  # type: ignore[arg-type]
        now=NOW,
    )


def test_a_link_round_trips_and_one_chain_has_one_active_link(uow_factory: UowFactory) -> None:
    rx, user = _chain(uow_factory)
    link = _link(rx, user.id)  # type: ignore[attr-defined]
    with uow_factory() as uow:
        uow.tenant(rx.clinic_id).patient_links.add(link)
        uow.commit()
    with uow_factory() as uow:
        links = uow.tenant(rx.clinic_id).patient_links
        assert links.get(link.id) == link
        assert links.active_for_prescription(rx.id) == link
        for _ in range(5):
            link.record_failure(LATER)
        links.update(link)
        uow.commit()
    with uow_factory() as uow:
        stored = uow.tenant(rx.clinic_id).patient_links.get(link.id, for_update=True)
        assert stored is not None and stored.is_locked and stored.locked_at == LATER

    second = _link(rx, user.id)  # type: ignore[attr-defined]
    with uow_factory() as uow, pytest.raises(IntegrityError, match="prescription_id_active"):
        uow.tenant(rx.clinic_id).patient_links.add(second)
    link.revoke(LATER)
    with uow_factory() as uow:
        links = uow.tenant(rx.clinic_id).patient_links
        links.update(link)
        links.add(second)  # allowed once the first is revoked
        uow.commit()
    with uow_factory() as uow:
        assert uow.tenant(rx.clinic_id).patient_links.active_for_prescription(rx.id) == second


def test_rate_limit_windows_count_per_bucket_and_old_ones_go(uow_factory: UowFactory) -> None:
    window = NOW.replace(second=0, microsecond=0)
    with uow_factory() as uow:
        assert [uow.rate_limits.hit("a", window_start=window) for _ in range(3)] == [1, 2, 3]
        assert uow.rate_limits.hit("b", window_start=window) == 1
        assert uow.rate_limits.hit("a", window_start=window + timedelta(minutes=1)) == 1
        uow.commit()
    with uow_factory() as uow:
        later = window + timedelta(hours=2)
        assert uow.rate_limits.hit("a", window_start=later) == 1
        uow.commit()
    with uow_factory() as uow:
        # The first window was removed by the later write, so counting starts again.
        assert uow.rate_limits.hit("a", window_start=window) == 1
