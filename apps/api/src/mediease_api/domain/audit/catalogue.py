"""How the owner's audit log names each action (M6a-P8, FR-AUD-03, decision 8A).

Every ``AuditAction`` has a category and a plain-English label; a unit test fails when an action
is added without one, so a new action never reaches an owner as a raw code. Labels say what
happened, never to whom: the row's record and person columns carry that. English at MVP.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mediease_api.domain.audit.actions import AuditAction as A
from mediease_api.domain.audit.event import ActorType


class AuditCategory(StrEnum):
    SIGN_IN = "SIGN_IN"
    TEAM = "TEAM"
    PATIENTS = "PATIENTS"
    APPOINTMENTS = "APPOINTMENTS"
    CLINICAL = "CLINICAL"
    PRESCRIPTIONS = "PRESCRIPTIONS"
    MESSAGES = "MESSAGES"
    SCHEDULE = "SCHEDULE"
    SETTINGS = "SETTINGS"


CATEGORY_LABELS: dict[AuditCategory, str] = {
    AuditCategory.SIGN_IN: "Sign-in",
    AuditCategory.TEAM: "Team",
    AuditCategory.PATIENTS: "Patients",
    AuditCategory.APPOINTMENTS: "Appointments",
    AuditCategory.CLINICAL: "Clinical records",
    AuditCategory.PRESCRIPTIONS: "Prescriptions and links",
    AuditCategory.MESSAGES: "Messages and reminders",
    AuditCategory.SCHEDULE: "Schedule",
    AuditCategory.SETTINGS: "Settings",
}


@dataclass(frozen=True, slots=True)
class ActionInfo:
    category: AuditCategory
    label: str


def _c(category: AuditCategory, *pairs: tuple[A, str]) -> dict[A, ActionInfo]:
    return {action: ActionInfo(category, label) for action, label in pairs}


ACTIONS: dict[A, ActionInfo] = {
    **_c(
        AuditCategory.SIGN_IN,
        (A.AUTH_SIGNED_IN, "Signed in"),
        (A.AUTH_SIGN_IN_FAILED, "Sign-in failed"),
        (A.AUTH_SIGNED_OUT, "Signed out"),
        (A.AUTH_REFRESH_REUSED, "Session reuse detected"),
        (A.STAFF_SIGNED_IN_GOOGLE, "Signed in with Google"),
        (A.AUTH_PASSWORD_RESET_REQUESTED, "Password reset requested"),
        (A.AUTH_PASSWORD_RESET, "Password reset"),
        (A.PATIENT_SIGNED_IN, "Patient signed in"),
        (A.PATIENT_SIGN_IN_FAILED, "Patient sign-in failed"),
        (A.PATIENT_SIGNED_OUT, "Patient signed out"),
        (A.PATIENT_REFRESH_REUSED, "Patient session reuse detected"),
        (A.PATIENT_PASSWORD_RESET, "Patient password reset"),
        (A.PATIENT_EMAIL_VERIFIED, "Patient email verified"),
        (A.PATIENT_ACCOUNT_CREATED, "Patient account created"),
    ),
    **_c(
        AuditCategory.TEAM,
        (A.STAFF_INVITED, "Invited a team member"),
        (A.STAFF_ACCEPTED, "Joined the team"),
        (A.STAFF_ROLE_CHANGED, "Changed a role"),
        (A.STAFF_DEACTIVATED, "Deactivated a team member"),
        (A.STAFF_REINVITED, "Invited a team member back"),
        (A.DOCTOR_ADDED, "Added a doctor"),
        (A.DOCTOR_UPDATED, "Changed a doctor's details"),
    ),
    **_c(
        AuditCategory.PATIENTS,
        (A.PATIENT_CREATED, "Registered a patient"),
        (A.PATIENT_UPDATED, "Changed a patient's details"),
        (A.PATIENT_CONSENT_CHANGED, "Changed messaging consent"),
        (A.PATIENT_OPTED_OUT, "Patient opted out of messages"),
        (A.PATIENT_OPTED_IN, "Patient opted back in"),
        (A.PATIENT_IMPORTED, "Imported a patient"),
    ),
    **_c(
        AuditCategory.APPOINTMENTS,
        (A.APPOINTMENT_BOOKED, "Booked an appointment"),
        (A.APPOINTMENT_CANCELLED, "Cancelled an appointment"),
        (A.APPOINTMENT_RESCHEDULED, "Rescheduled an appointment"),
        (A.APPOINTMENT_STATUS_CHANGED, "Moved a patient in the queue"),
    ),
    **_c(
        AuditCategory.CLINICAL,
        (A.VISIT_STARTED, "Started a consultation"),
        (A.VISIT_UPDATED, "Changed consultation notes"),
        (A.VISIT_COMPLETED, "Completed a consultation"),
        (A.VISIT_ADDENDUM_ADDED, "Added an addendum"),
        (A.VISIT_VIEWED, "Viewed a consultation"),
        (A.PATIENT_VISITS_VIEWED, "Viewed a patient's visits"),
    ),
    **_c(
        AuditCategory.PRESCRIPTIONS,
        (A.PRESCRIPTION_CREATED, "Started a prescription"),
        (A.PRESCRIPTION_UPDATED, "Changed a draft prescription"),
        (A.PRESCRIPTION_DISCARDED, "Discarded a draft prescription"),
        (A.PRESCRIPTION_ISSUED, "Issued a prescription"),
        (A.PRESCRIPTION_REVISED, "Revised a prescription"),
        (A.PRESCRIPTION_VIEWED, "Viewed a prescription"),
        (A.PRESCRIPTION_PDF_DOWNLOADED, "Downloaded or printed a prescription"),
        (A.PRESCRIPTION_LINK_EXPIRED, "Prescription link not sent"),
        (A.PATIENT_LINK_OPENED, "Patient opened a prescription link"),
        (A.PATIENT_LINK_CHALLENGE_FAILED, "Wrong answer on a prescription link"),
        (A.PATIENT_LINK_LOCKED, "Prescription link locked"),
        (A.PATIENT_LINK_CREATED, "Created a prescription link"),
        (A.PATIENT_LINK_RESET, "Unlocked a prescription link"),
        (A.PATIENT_LINK_REPLACED, "Replaced a prescription link"),
        (A.RX_FAVOURITE_CREATED, "Saved a favourite"),
        (A.RX_FAVOURITE_UPDATED, "Changed a favourite"),
        (A.RX_FAVOURITE_DELETED, "Deleted a favourite"),
        (A.RX_TEMPLATE_CREATED, "Saved a template"),
        (A.RX_TEMPLATE_UPDATED, "Changed a template"),
        (A.RX_TEMPLATE_DELETED, "Deleted a template"),
    ),
    **_c(
        AuditCategory.MESSAGES,
        (A.REMINDER_SCHEDULED, "Scheduled a reminder"),
        (A.REMINDER_RESCHEDULED, "Moved a reminder"),
        (A.REMINDER_CANCELLED, "Cancelled a reminder"),
    ),
    **_c(
        AuditCategory.SCHEDULE,
        (A.SCHEDULE_CHANGED, "Changed a weekly schedule"),
        (A.SCHEDULE_EXCEPTION_ADDED, "Added leave or an extra session"),
        (A.SCHEDULE_EXCEPTION_REMOVED, "Removed leave or an extra session"),
    ),
    **_c(
        AuditCategory.SETTINGS,
        (A.CLINIC_CREATED, "Created the clinic"),
        (A.CLINIC_ACTIVATED, "Activated the clinic"),
        (A.CLINIC_UPDATED, "Changed clinic settings"),
        (A.NOTIFICATION_PREFERENCES_CHANGED, "Changed notification settings"),
        (A.RETENTION_PURGED, "Deleted expired data"),
        (A.AUDIT_EXPORTED, "Exported the audit log"),
    ),
}

# Who did it, when the actor is not a named member of this clinic.
ACTOR_LABELS: dict[ActorType, str] = {
    ActorType.OPS: "MediEase support",
    ActorType.SYSTEM: "System",
    ActorType.PATIENT_LINK: "Patient (prescription link)",
    ActorType.PATIENT: "Patient (portal)",
}


def actions_in(categories: frozenset[AuditCategory]) -> list[str]:
    """The action names of ``categories``, sorted, for a filter."""
    return sorted(a.value for a, info in ACTIONS.items() if info.category in categories)


def describe(action: str) -> ActionInfo:
    """An action as the owner reads it; an unknown name (a retired action) shows as itself."""
    try:
        return ACTIONS[A(action)]
    except ValueError:
        return ActionInfo(AuditCategory.SETTINGS, action)
