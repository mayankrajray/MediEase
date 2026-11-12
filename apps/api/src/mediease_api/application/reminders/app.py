"""Reminders in the app (M7e-E4; spec web-push R40-R46).

The clinic's reminders (before a booked visit, and a follow-up) go to the patient's app account
too: the account actively linked to the record (R56; accepting a booking request links it). Each
reminder is one notice, in the app and by push, at the reminder's own time, so it follows every
rule a WhatsApp reminder does: the same due times, quiet hours, and cancellation or move with its
appointment. The notice's key is the reminder, so a reminder tells the account at most once,
whatever the retries.

WhatsApp is unchanged: a consenting patient still gets the message as well. A patient who cannot
be messaged on WhatsApp but was told in the app ends ``SENT_IN_APP`` instead of
``SKIPPED_NO_CONSENT``, so the desk does not need to call.
"""

from __future__ import annotations

from datetime import datetime

from mediease_api.application.portal.patient_notifications import (
    APPOINTMENTS_LINK,
    deliver_patient_notice,
    linked_account,
    place_params,
)
from mediease_api.domain.appointments.appointment import Appointment
from mediease_api.domain.patients.patient import Patient
from mediease_api.domain.portal.notifications import PatientNotificationKind
from mediease_api.domain.reminders.reminder import Reminder
from mediease_api.domain.scheduling.sessions import Session
from mediease_api.ports.ids import IdPort
from mediease_api.ports.unit_of_work import TenantRepositories, UnitOfWork


def reminder_key(kind: PatientNotificationKind, reminder: Reminder) -> str:
    return f"{kind.value}:{reminder.id}"


def can_remind(tenant: TenantRepositories, patient: Patient) -> bool:
    """R40: WhatsApp consent, or an app account linked to the record."""
    return patient.may_receive_whatsapp or linked_account(tenant, patient.id) is not None


def remind_in_app(
    uow: UnitOfWork,
    tenant: TenantRepositories,
    *,
    ids: IdPort,
    reminder: Reminder,
    appointment: Appointment | None,
    session: Session | None,
    now: datetime,
    request_id: str | None,
) -> bool:
    """R41, R42: tell the linked account, in the caller's transaction; whether it was reached."""
    account = linked_account(tenant, reminder.patient_id)
    if account is None:
        return False
    if reminder.follows_appointment:
        assert appointment is not None and session is not None
        kind = PatientNotificationKind.APPOINTMENT_REMINDER
        params = place_params(appointment, session)
        entity = ("appointment", appointment.id)
    else:
        kind = PatientNotificationKind.FOLLOW_UP_DUE
        params = {
            "date": reminder.follow_up_date.isoformat(),
            "doctor_id": str(reminder.doctor_id),
        }
        entity = ("reminder", reminder.id)
    return deliver_patient_notice(
        uow,
        tenant,
        ids=ids,
        account_id=account,
        kind=kind,
        event_key=reminder_key(kind, reminder),
        entity=entity,
        link=APPOINTMENTS_LINK,
        params=params,
        now=now,
        request_id=request_id,
    ).reached
