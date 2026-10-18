/** Test data for the queue and booking screens: invented people and clinics only (M3-P5). */

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { patient } from "@/features/patients/testing";
import { workspaceRoutes } from "@/features/patients/testing";
import { clinicToday } from "@/features/patients/fields";
import { json } from "@/test/api";

import type { Appointment, Doctor, DoctorSession } from "@/features/appointments/api";
import type { Queue } from "./useQueue";

export const DOCTOR_ID = "0192f0a0-0000-7000-8000-0000000000d1";
export const OTHER_DOCTOR_ID = "0192f0a0-0000-7000-8000-0000000000d2";
export const SESSION_ID = "0192f0a0-0000-7000-8000-0000000000e1";

export const deskWithQueue = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "APPOINTMENTS_MANAGE", "QUEUE_MOVE"],
});

export function doctor(overrides: Partial<Doctor> = {}): Doctor {
  return {
    id: DOCTOR_ID,
    user_id: null,
    display_name: "Dr Meera Iyer",
    qualification: "MBBS",
    registration_number: "MCI-0001",
    registration_council: "Sample Council",
    specialty: null,
    is_active: true,
    ...overrides,
  };
}

const minutes = (n: number) => new Date(Date.now() + n * 60_000).toISOString();
export const today = () => clinicToday("Asia/Kolkata");

/** A session running now: started ten minutes ago, for an hour. */
export function session(overrides: Partial<DoctorSession> = {}): DoctorSession {
  return {
    id: SESSION_ID,
    doctor_id: DOCTOR_ID,
    on_date: today(),
    starts_at: minutes(-10),
    ends_at: minutes(50),
    mode: "TOKENS",
    status: "OPEN",
    slot_minutes: null,
    capacity: 12,
    booked_count: 1,
    available: 11,
    next_token: 2,
    slots: [],
    ...overrides,
  };
}

export function appointment(overrides: Partial<Appointment> = {}): Appointment {
  const s = session();
  return {
    id: "0192f0a0-0000-7000-8000-0000000000f1",
    session_id: s.id,
    doctor_id: DOCTOR_ID,
    patient_id: patient().id,
    on_date: s.on_date,
    session_starts_at: s.starts_at,
    session_ends_at: s.ends_at,
    mode: "TOKENS",
    slot_start: null,
    token_number: 1,
    status: "BOOKED",
    source: "FRONT_DESK",
    reason: null,
    cancel_reason: null,
    cancel_note: null,
    cancelled_at: null,
    rescheduled_from_id: null,
    arrived_at: null,
    started_at: null,
    completed_at: null,
    created_by: null,
    created_at: minutes(-60),
    updated_at: minutes(-60),
    ...overrides,
  };
}

export function queueOf(entries: readonly Partial<Appointment>[], name = "Asha Rao"): Queue {
  return {
    on_date: today(),
    sessions: [
      {
        ...session(),
        appointments: entries.map((e, i) => ({
          ...appointment({ id: `0192f0a0-0000-7000-8000-00000000010${i}`, token_number: i + 1, ...e }),
          patient: { id: patient().id, code: `SC-000${i + 1}`, full_name: i === 0 ? name : `Patient ${i + 1}`, age_years: 40, sex: "FEMALE" },
          wait_minutes: e.status === "ARRIVED" ? 0 : null,
          visit_id: null,
          prescription: null,
        })),
      },
    ],
  };
}

/** The workspace routes, with a front desk who may book and move the queue, and the doctors. */
export const boardRoutes = {
  ...workspaceRoutes,
  "GET /api/v1/me": () => json(200, person([deskWithQueue])),
  "GET /api/v1/clinic/doctors": () => json(200, { items: [doctor()] }),
};
