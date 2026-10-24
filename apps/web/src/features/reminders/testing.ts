/** Test data for the reminder and message screens (M5-P6): invented people and clinics only. */

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { PATIENT_ID, workspaceRoutes } from "@/features/patients/testing";
import { DOCTOR_ID, doctor } from "@/features/queue/testing";
import { json } from "@/test/api";

import type { PatientMessage, PendingFollowUp, Reminder } from "./api";

export const REMINDER_ID = "0192f0a0-0000-7000-8000-0000000006a1";
export const CHAIN_ID = "0192f0a0-0000-7000-8000-0000000003b1";

export const deskWithReminders = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "APPOINTMENTS_MANAGE", "QUEUE_MOVE", "REMINDERS_SCHEDULE"],
});

export function reminder(overrides: Partial<Reminder> = {}): Reminder {
  return {
    id: REMINDER_ID,
    patient_id: PATIENT_ID,
    doctor_id: DOCTOR_ID,
    kind: "FOLLOW_UP",
    source: "PRESCRIPTION",
    prescription_id: CHAIN_ID,
    appointment_id: null,
    follow_up_date: "2026-10-20",
    due_at: "2026-10-19T03:30:00+00:00", // 09:00 IST
    status: "SCHEDULED",
    error_code: null,
    revision: 1,
    created_at: "2026-10-12T05:00:00+00:00",
    cancelled_at: null,
    ...overrides,
  };
}

export function message(overrides: Partial<PatientMessage> = {}): PatientMessage {
  return {
    id: "0192f0a0-0000-7000-8000-0000000007a1",
    template_key: "booking_confirmed",
    source_type: "APPOINTMENT",
    source_id: "0192f0a0-0000-7000-8000-0000000000f1",
    channel: "WHATSAPP",
    status: "DELIVERED",
    error_code: null,
    created_at: "2026-10-12T05:00:00+00:00",
    sent_at: "2026-10-12T05:00:01+00:00",
    delivered_at: "2026-10-12T05:00:05+00:00",
    read_at: null,
    failed_at: null,
    ...overrides,
  };
}

export function pending(overrides: Partial<PendingFollowUp> = {}): PendingFollowUp {
  return {
    patient_id: PATIENT_ID,
    patient_code: "SC-0004",
    patient_name: "Bina Shah",
    doctor_id: DOCTOR_ID,
    prescription_id: CHAIN_ID,
    visit_id: "0192f0a0-0000-7000-8000-0000000002a1",
    follow_up_date: "2026-10-17",
    reminder_status: "DELIVERED",
    ...overrides,
  };
}

/** The workspace for a front desk who may schedule reminders and book, with one doctor. */
export const reminderRoutes = {
  ...workspaceRoutes,
  "GET /api/v1/me": () => json(200, person([deskWithReminders])),
  "GET /api/v1/clinic/doctors": () => json(200, { items: [doctor()] }),
};
