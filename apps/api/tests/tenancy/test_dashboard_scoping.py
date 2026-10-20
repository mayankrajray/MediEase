"""The *Today* counts never mix clinics (M6-P1; NFR-08, ADR-0003).

``SqlAlchemyDashboardReads`` is not a ``TenantScopedRepository`` (it counts across several tables,
not one model), so its scoping is proved here: bound to clinic A, it behaves as if clinic B's
sessions, appointments, patients and messages do not exist, even when it is handed B's IDs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession, Session
from mediease_api.domain.shared.time import local_date
from tests.builders import new_id
from tests.conftest import UowFactory
from tests.tenancy.test_repository_scoping import (  # noqa: F401 (the fixture)
    Tenant,
    _a_message,
    two_clinics,
)

ZONE = "Asia/Kolkata"


def _booked_today(uow_factory: UowFactory, tenant: Tenant, now: datetime) -> Session:
    """A session starting now for the tenant's doctor, with its patient booked and messaged."""
    plan = PlannedSession(
        tenant.doctor.id,
        local_date(now, ZONE),
        now,
        now + timedelta(hours=1),
        BookingMode.TOKENS,
        None,
        5,
    )
    with uow_factory() as uow:
        staff = uow.tenant(tenant.clinic_id)
        session = Session.from_plan(plan, id=new_id(), clinic_id=tenant.clinic_id, now=now)
        staff.sessions.add_missing([session])
        appointment = Appointment.book(
            session, id=new_id(), patient_id=tenant.patient.id, active=[], now=now
        )
        staff.sessions.update(session)
        staff.appointments.add(appointment)
        message = _a_message(tenant, appointment.id)
        message.fail("WA_TEST_FAILURE", now)
        staff.messages.add(message)
        uow.commit()
    return session


def test_nfr_08_m6_p1_clinic_a_never_counts_clinic_b(
    uow_factory: UowFactory,
    two_clinics: tuple[Tenant, Tenant],  # noqa: F811
) -> None:
    a, b = two_clinics
    now = datetime.now(UTC).replace(microsecond=0)
    today = local_date(now, ZONE)
    session_b = _booked_today(uow_factory, b, now)

    with uow_factory() as uow:
        reads = uow.tenant(a.clinic_id).dashboard
        # Handed B's session, A's reads find nothing in it.
        assert reads.status_counts_by_session([session_b.id]) == {}
        assert reads.next_patients([session_b.id], limit=3) == []
        assert (
            reads.failed_message_count(since=now - timedelta(hours=1), until=now + timedelta(1))
            == 0
        )
        assert reads.pending_follow_up_count(today=today, timezone=ZONE) == 0
        week = reads.week(
            first=today - timedelta(days=6), last=today, doctor_id=None, timezone=ZONE
        )
        assert [(d.appointments, d.messages_sent) for d in week] == [(0, 0)] * 7
        assert (
            reads.week(first=today, last=today, doctor_id=b.doctor.id, timezone=ZONE)[
                0
            ].appointments
            == 0
        )

    with uow_factory() as uow:
        reads = uow.tenant(b.clinic_id).dashboard
        [counts] = reads.status_counts_by_session([session_b.id]).values()
        assert (counts.total, counts.not_arrived) == (1, 1)
        [nxt] = reads.next_patients([session_b.id], limit=3)
        assert (nxt.patient_first_name, nxt.status, nxt.token_number) == ("Asha", "BOOKED", 1)
        assert (
            reads.failed_message_count(since=now - timedelta(hours=1), until=now + timedelta(1))
            == 1
        )
        [day] = reads.week(first=today, last=today, doctor_id=None, timezone=ZONE)
        assert (day.appointments, day.completed, day.no_show, day.messages_sent) == (1, 0, 0, 0)
