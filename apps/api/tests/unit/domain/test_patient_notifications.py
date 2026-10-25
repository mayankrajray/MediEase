"""Patient notices and the live queue position (M6b-P6; portal R55, R59, R63, R70; AC25, AC27)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.appointments.live import LiveState, live_view
from mediease_api.domain.appointments.status import AppointmentStatus
from mediease_api.domain.links.token import (
    Kind,
    QueueClaims,
    queue_claims_bytes,
    read_queue_claims,
    split,
)
from mediease_api.domain.patients.patient import Language
from mediease_api.domain.portal.notifications import (
    Names,
    PatientChannel,
    PatientNotification,
    PatientNotificationKind,
    booking_email,
    check_channel,
    render_title,
)
from mediease_api.domain.scheduling.mode import BookingMode
from mediease_api.domain.scheduling.sessions import PlannedSession, Session
from mediease_api.domain.shared.errors import InvalidValue
from tests.builders import new_id

NOW = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)
NAMES = Names("Sample Clinic", "Dr. Mehta", "Asia/Kolkata")
K = PatientNotificationKind


def notice(kind: PatientNotificationKind, **params: str) -> PatientNotification:
    return PatientNotification.create(
        id=new_id(),
        clinic_id=new_id(),
        account_id=new_id(),
        kind=kind,
        event_key=f"{kind.value}:{new_id()}",
        entity=("booking_request", new_id()),
        link="/portal/appointments",
        params=params,
        now=NOW,
    )


def test_r55_titles_are_rendered_in_the_accounts_language() -> None:
    n = notice(K.BOOKING_ACCEPTED, at="2026-10-27T05:30:00+00:00")
    assert (
        render_title(n, NAMES, Language.EN)
        == "Booked: 27 Oct, 11:00 with Dr. Mehta at Sample Clinic"
    )
    hindi = render_title(n, NAMES, Language.HI)
    assert "बुक हो गया" in hindi and "अक्टू" in hindi
    token = notice(K.APPOINTMENT_CONFIRMED, at="2026-10-27T04:30:00+00:00", token="4")
    assert (
        render_title(token, NAMES, Language.EN)
        == "Appointment confirmed: 27 Oct, token 4 with Dr. Mehta"
    )
    due = notice(K.MEDICINE_DUE, slot="MORNING", time="08:00")
    assert render_title(due, NAMES, Language.EN) == "Morning medicines · 08:00"
    assert render_title(due, NAMES, Language.HI) == "सुबह की दवाइयाँ · 08:00"


def test_r59_r63_the_decline_reason_is_in_the_app_never_in_the_email() -> None:
    n = notice(K.BOOKING_DECLINED, reason="DOCTOR_UNAVAILABLE")
    assert "the doctor is not available then" in render_title(n, NAMES, Language.EN)
    email = booking_email(K.BOOKING_DECLINED, NAMES, Language.EN, "https://example.test/portal")
    assert email.subject.startswith("Booking declined at Sample Clinic")
    assert "doctor" not in email.text.lower() and "available" not in email.text.lower()
    assert "https://example.test/portal" in email.text


def test_r55_a_notice_holds_ids_and_a_time_only() -> None:
    with pytest.raises(InvalidValue):
        notice(K.PRESCRIPTION_READY, medicine="Tab X")
    with pytest.raises(InvalidValue):
        PatientNotification.create(
            id=new_id(),
            clinic_id=new_id(),
            account_id=new_id(),
            kind=K.MEDICINE_DUE,
            event_key="k",
            entity=("x", new_id()),
            link="https://evil.example",
            params={},
            now=NOW,
        )


def test_r63_email_is_only_for_booking_answers() -> None:
    check_channel(K.BOOKING_EXPIRED, PatientChannel.EMAIL)
    check_channel(K.MEDICINE_DUE, PatientChannel.IN_APP)
    with pytest.raises(InvalidValue):
        check_channel(K.MEDICINE_DUE, PatientChannel.EMAIL)


# --- The live queue (R70, AC27) ------------------------------------------------------------------

STARTS = datetime(2026, 10, 26, 4, 30, tzinfo=UTC)


def _session() -> Session:
    plan = PlannedSession(
        new_id(),
        date(2026, 10, 26),
        STARTS,
        STARTS + timedelta(hours=3),
        BookingMode.TOKENS,
        None,
        12,
    )
    return Session.from_plan(plan, id=new_id(), clinic_id=new_id(), now=STARTS - timedelta(days=1))


def _token(session: Session, n: int, status: AppointmentStatus) -> Appointment:
    a = Appointment.book(
        session, id=new_id(), patient_id=new_id(), active=[], now=STARTS - timedelta(days=1)
    )
    a.token_number = n
    a.status = status
    return a


def test_ac27_ahead_counts_only_booked_and_arrived_before_me() -> None:
    s = _session()
    rows = [
        _token(s, 3, AppointmentStatus.IN_CONSULTATION),
        _token(s, 4, AppointmentStatus.ARRIVED),
        _token(s, 5, AppointmentStatus.BOOKED),
        _token(s, 6, AppointmentStatus.CANCELLED),
        _token(s, 2, AppointmentStatus.COMPLETED),
        _token(s, 1, AppointmentStatus.NO_SHOW),
    ]
    mine = _token(s, 7, AppointmentStatus.BOOKED)
    view = live_view(mine, s, [*rows, mine], STARTS + timedelta(minutes=30))
    assert (view.state, view.ahead, view.now_seeing_token) == (LiveState.WAITING, 2, 3)


def test_ac27_your_turn_done_cancelled_and_not_started() -> None:
    s = _session()
    me = _token(s, 5, AppointmentStatus.IN_CONSULTATION)
    assert live_view(me, s, [me], STARTS).state is LiveState.YOUR_TURN
    me.status = AppointmentStatus.COMPLETED
    assert live_view(me, s, [me], STARTS).state is LiveState.DONE
    me.status = AppointmentStatus.CANCELLED
    assert live_view(me, s, [me], STARTS).state is LiveState.CANCELLED
    me.status = AppointmentStatus.BOOKED
    early = live_view(me, s, [me], STARTS - timedelta(hours=1))
    assert (early.state, early.ahead) == (LiveState.NOT_STARTED, 0)


def test_adr_0019_a_queue_token_is_its_own_kind() -> None:
    claims = QueueClaims(
        cid=new_id(),
        aid=new_id(),
        nbf=NOW.replace(microsecond=0),
        exp=(NOW + timedelta(hours=5)).replace(microsecond=0),
    )
    raw = queue_claims_bytes(claims)
    assert len(raw) == 40
    from mediease_api.domain.links import token as t

    signing = t.signing_input(Kind.QUEUE, "k1", raw)
    parts = split(t.assemble(signing, b"x" * 16))
    assert read_queue_claims(parts) == claims
