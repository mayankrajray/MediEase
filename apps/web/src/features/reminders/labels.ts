/**
 * Words for reminder and message statuses, and plain explanations of why a message did not
 * arrive (M5-P6 decision 5A; spec §6 "Failed messages show a plain explanation"). No error code
 * reaches the screen raw: an unknown one gets a general sentence.
 */

import type { PatientMessage, ReminderStatus } from "./api";

export const REMINDER_STATUS_LABELS: Record<ReminderStatus, string> = {
  SCHEDULED: "Scheduled",
  SENT: "Sent",
  DELIVERED: "Delivered",
  READ: "Read",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
  SKIPPED_NO_CONSENT: "Not sent: no consent",
};

export const MESSAGE_STATUS_LABELS: Record<PatientMessage["status"], string> = {
  QUEUED: "Waiting to send",
  SENT: "Sent",
  DELIVERED: "Delivered",
  READ: "Read",
  FAILED: "Not delivered",
};

export const CHANNEL_LABELS: Record<PatientMessage["channel"], string> = {
  WHATSAPP: "WhatsApp",
  SMS: "SMS",
  CONSOLE: "Test (not sent)",
};

const TEMPLATE_LABELS: Record<string, string> = {
  booking_confirmed: "Appointment confirmation",
  rx_ready: "Prescription link",
  rx_updated: "Updated prescription link",
  follow_up_due: "Follow-up reminder",
  opt_out_confirmed: "Reply to their STOP",
  // M6a-P8: before a booked visit, and a visit the clinic cancelled.
  appointment_reminder: "Appointment reminder",
  appointment_cancelled: "Cancellation notice",
};

export function templateLabel(key: string): string {
  return TEMPLATE_LABELS[key] ?? "Message";
}

const EXPLANATIONS: Record<string, string> = {
  MSG_RECIPIENT_INVALID: "This number can't receive WhatsApp.",
  MSG_NO_CONSENT: "Not sent: the patient hasn't agreed to messages or asked to stop.",
  MSG_OUTCOME_UNKNOWN: "We can't tell whether it arrived, so it was not sent again.",
  MSG_PROVIDER_UNAVAILABLE: "WhatsApp was unavailable and the message could not be sent.",
  MSG_PROVIDER_RATE_LIMIT: "WhatsApp was busy and the message could not be sent.",
  MSG_PROVIDER_REJECTED: "WhatsApp refused the message.",
  MSG_PROVIDER_AUTH: "Messaging is not set up correctly. Tell MediEase support.",
  MSG_TEMPLATE_NOT_FOUND: "This message is not approved yet. Tell MediEase support.",
  MSG_TEMPLATE_PARAMS: "This message could not be prepared. Tell MediEase support.",
  MSG_NOT_APPLICABLE: "Not sent: it no longer applied.",
  REM_CLINIC_PHONE_MISSING: "Not sent: the clinic has no phone number in its settings.",
  // M6a-P8: an appointment reminder the system cancelled when it was due.
  REM_APPOINTMENT_CHANGED: "Not sent: the appointment changed (cancelled, moved, arrived or closed by leave).",
  REM_TOO_LATE: "Not sent: it was too close to the visit.",
};

/** The sentence for a failed or skipped message or reminder; null when nothing went wrong. */
export function explainFailure(status: string, code: string | null): string | null {
  if (status === "SKIPPED_NO_CONSENT") return EXPLANATIONS.MSG_NO_CONSENT ?? null;
  // M6a-P8: the system cancelled an appointment reminder when it was due; say why.
  if (status === "CANCELLED") return code !== null ? (EXPLANATIONS[code] ?? null) : null;
  if (status !== "FAILED") return null;
  return (code !== null ? EXPLANATIONS[code] : undefined) ?? "The message could not be delivered.";
}

/** A failure staff can make up for with a phone call (not a configuration problem). */
export function shouldCall(status: string): boolean {
  return status === "FAILED" || status === "SKIPPED_NO_CONSENT";
}
