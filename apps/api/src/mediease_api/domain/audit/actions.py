"""The catalogue of audited actions (FR-AUD-01, spec §7).

One closed set, so a typo cannot invent an action name and "where is
``staff.role_changed`` written?" is a single grep. Names follow the log
convention ``area.past_tense`` (apps/api/CLAUDE.md), because an audit action
is always something that already happened.

Actions are added in the phase that first writes them; M1-P4 covers the
session events and the staff role change, M1-P5 the onboarding and staff
management actions (spec §7).
"""

from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    AUTH_SIGNED_IN = "auth.signed_in"
    # Only for a known account: the unknown-identifier path has no lockout, so
    # auditing it would let an anonymous caller grow the table without bound.
    AUTH_SIGN_IN_FAILED = "auth.sign_in_failed"
    AUTH_SIGNED_OUT = "auth.signed_out"
    # A rotated refresh token was presented again: possible token theft (R5).
    AUTH_REFRESH_REUSED = "auth.refresh_reused"
    # M1-P5: onboarding and staff management.
    CLINIC_CREATED = "clinic.created"
    CLINIC_ACTIVATED = "clinic.activated"
    CLINIC_UPDATED = "clinic.updated"
    DOCTOR_ADDED = "doctor.added"
    DOCTOR_UPDATED = "doctor.updated"
    STAFF_INVITED = "staff.invited"
    STAFF_ACCEPTED = "staff.accepted"
    STAFF_ROLE_CHANGED = "staff.role_changed"
    STAFF_DEACTIVATED = "staff.deactivated"
    # M6a-P5: a deactivated member invited back (DEACTIVATED -> INVITED). Like staff.invited, the
    # metadata holds the target user, the role and the delivery (email or link); never an address.
    STAFF_REINVITED = "staff.reinvited"
    # M2-P2: patients. Metadata holds the code and field names, never a name or a phone number.
    PATIENT_CREATED = "patient.created"
    PATIENT_UPDATED = "patient.updated"
    # M2-P3: consent is evidence (DPDP). Metadata holds the flags and on whose behalf, no names.
    PATIENT_CONSENT_CHANGED = "patient.consent_changed"
    PATIENT_OPTED_OUT = "patient.opted_out"
    PATIENT_OPTED_IN = "patient.opted_in"
    # M2-P4: one row per imported patient, by the ops user. Metadata: the code and the import ID.
    PATIENT_IMPORTED = "patient.imported"
    # M3-P1: schedules. Metadata: counts, dates and kinds only.
    SCHEDULE_CHANGED = "schedule.changed"
    SCHEDULE_EXCEPTION_ADDED = "schedule.exception_added"
    SCHEDULE_EXCEPTION_REMOVED = "schedule.exception_removed"
    # M3-P2: bookings. Metadata: IDs, mode, token or slot, source and cancel reason; never a name,
    # the appointment's reason or the cancel note.
    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    # M3-P3: the queue. Metadata: from, to, session and doctor IDs.
    APPOINTMENT_STATUS_CHANGED = "appointment.status_changed"
    # M4-P1: visits (spec prescriptions R16, R17). Metadata: IDs, revisions, counts and the names of
    # changed fields, never their values. Reads are one row per logical view, never per entity.
    VISIT_STARTED = "visit.started"
    VISIT_UPDATED = "visit.updated"
    VISIT_COMPLETED = "visit.completed"
    VISIT_ADDENDUM_ADDED = "visit.addendum_added"
    VISIT_VIEWED = "visit.viewed"
    PATIENT_VISITS_VIEWED = "patient.visits_viewed"
    # M4-P2: prescriptions. Metadata: visit, version, revision, counts, language and delivery
    # state; never a medicine, a dose or advice text (R17).
    PRESCRIPTION_CREATED = "prescription.created"
    PRESCRIPTION_UPDATED = "prescription.updated"
    PRESCRIPTION_DISCARDED = "prescription.discarded"
    PRESCRIPTION_ISSUED = "prescription.issued"
    PRESCRIPTION_REVISED = "prescription.revised"
    PRESCRIPTION_VIEWED = "prescription.viewed"
    # M4-P4: one row per PDF download (R16, spec D6). Metadata: visit, version, paper size, the
    # caller's role and whether this download rendered it; never content.
    PRESCRIPTION_PDF_DOWNLOADED = "prescription.pdf_downloaded"
    # M4-P5: patient links (R13). Metadata: the link's ID, the version shown, the language, an
    # attempt number; never digits, a phone number or content. Patients act as PATIENT_LINK.
    PATIENT_LINK_OPENED = "patient_link.opened"
    PATIENT_LINK_CHALLENGE_FAILED = "patient_link.challenge_failed"
    PATIENT_LINK_LOCKED = "patient_link.locked"
    PATIENT_LINK_CREATED = "patient_link.created"
    PATIENT_LINK_RESET = "patient_link.reset"
    PATIENT_LINK_REPLACED = "patient_link.replaced"
    # M4-P3: a doctor's favourites and templates. Metadata: none (the entity ID says which);
    # never a name or a medicine. Lists and suggestions are not audited (decision 4A).
    RX_FAVOURITE_CREATED = "rx_favourite.created"
    RX_FAVOURITE_UPDATED = "rx_favourite.updated"
    RX_FAVOURITE_DELETED = "rx_favourite.deleted"
    RX_TEMPLATE_CREATED = "rx_template.created"
    RX_TEMPLATE_UPDATED = "rx_template.updated"
    RX_TEMPLATE_DELETED = "rx_template.deleted"
    # M5-P1: the platform's retention purge, written as SYSTEM. Metadata: row counts only.
    RETENTION_PURGED = "retention.purged"
    # M5-P2 (prescriptions R15): a pending link not sent, written as SYSTEM. Metadata: the
    # version and the reason (``too_old``, ``no_consent`` or ``no_link``).
    PRESCRIPTION_LINK_EXPIRED = "prescription.link_expired"
    # M5-P4 (spec §7): reminders. Metadata: the patient, doctor, source, follow-up date and
    # revision; written as STAFF, or as SYSTEM when a prescription's revision cancels one.
    REMINDER_SCHEDULED = "reminder.scheduled"
    REMINDER_RESCHEDULED = "reminder.rescheduled"
    REMINDER_CANCELLED = "reminder.cancelled"
    # M6a-P3 (ADR-0015): patient accounts, written as PATIENT on the ``patient_account`` entity,
    # and staff Google sign-in, written as STAFF. Metadata: the sign-in method, the session ID,
    # whether a Google identity was linked now, a failure reason; never an email or a name.
    PATIENT_ACCOUNT_CREATED = "patient_account.created"
    PATIENT_SIGNED_IN = "patient.signed_in"
    PATIENT_SIGN_IN_FAILED = "patient.sign_in_failed"
    PATIENT_SIGNED_OUT = "patient.signed_out"
    PATIENT_REFRESH_REUSED = "patient.refresh_reused"
    STAFF_SIGNED_IN_GOOGLE = "staff.signed_in_google"
    # M6a-P4 (ADR-0016): password reset and email verification. Written as STAFF or PATIENT about
    # the account itself. Metadata: which email, how many sessions a reset ended; never an
    # address or a token. A request for an address with no account writes nothing.
    AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
    AUTH_PASSWORD_RESET = "auth.password_reset"
    PATIENT_PASSWORD_RESET = "patient.password_reset"
    PATIENT_EMAIL_VERIFIED = "patient.email_verified"
