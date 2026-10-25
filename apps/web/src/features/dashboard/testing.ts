/** Test data for the Today screen (M6-P1): invented people, codes and doctors only. */

import { addDays } from "@/lib/format/time";
import { today as clinicDay } from "@/features/queue/testing";

import type { Today } from "./useToday";

export const SESSION_ID = "0192f0a0-0000-7000-8000-0000000000e1";
export const DOCTOR_ID = "0192f0a0-0000-7000-8000-0000000000d1";

const counts = (overrides: Partial<Today["counts"]> = {}): Today["counts"] => {
  const c = { not_arrived: 2, waiting: 3, in_consultation: 1, completed: 4, no_show: 1, ...overrides };
  return { ...c, total: c.not_arrived + c.waiting + c.in_consultation + c.completed + c.no_show };
};

export function todayOf(overrides: Partial<Today> = {}): Today {
  const on = clinicDay();
  return {
    on_date: on,
    scope: "CLINIC",
    doctor_id: null,
    counts: counts(),
    sessions: [
      {
        id: SESSION_ID,
        doctor_id: DOCTOR_ID,
        doctor_name: "Dr Meera Iyer",
        starts_at: "2026-10-20T04:30:00+00:00",
        ends_at: "2026-10-20T07:30:00+00:00",
        status: "OPEN",
        mode: "TOKENS",
        capacity: 20,
        counts: counts(),
      },
    ],
    next_patients: [
      {
        appointment_id: "0192f0a0-0000-7000-8000-000000000101",
        session_id: SESSION_ID,
        doctor_id: DOCTOR_ID,
        status: "ARRIVED",
        token_number: 4,
        slot_start: null,
        patient_code: "SC-0004",
        patient_first_name: "Asha",
      },
      {
        appointment_id: "0192f0a0-0000-7000-8000-000000000102",
        session_id: SESSION_ID,
        doctor_id: DOCTOR_ID,
        status: "BOOKED",
        token_number: null,
        slot_start: "2026-10-20T05:00:00+00:00",
        patient_code: "SC-0007",
        patient_first_name: "Bina",
      },
    ],
    follow_ups_pending: 2,
    bookings_to_move: 0,
    messages_failed: 1,
    week: null,
    booking_requests_open: null,
    requests_answered_30d: null,
    requests_expired_30d: null,
    ...overrides,
  };
}

/** Seven days ending on the clinic's today, oldest first. */
export function weekOf(perDay: (i: number) => Partial<NonNullable<Today["week"]>[number]> = () => ({})) {
  const end = clinicDay();
  return Array.from({ length: 7 }, (_, i) => ({
    on_date: addDays(end, i - 6),
    appointments: 0,
    completed: 0,
    no_show: 0,
    messages_sent: 0,
    ...perDay(i),
  }));
}
