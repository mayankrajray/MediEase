/** Test data for the consultation screen (M4-P6): invented people, clinics and medicines only. */

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { patient, workspaceRoutes } from "@/features/patients/testing";
import type { Consultation, PatientPage, Prescription, Visit, VisitSummary } from "@/features/prescriptions/api";
import { DOCTOR_ID, doctor } from "@/features/queue/testing";
import { json } from "@/test/api";

export const VISIT_ID = "0192f0a0-0000-7000-8000-0000000002a1";
export const EARLIER_ID = "0192f0a0-0000-7000-8000-0000000002a0";
export const RX_ID = "0192f0a0-0000-7000-8000-0000000003b1";
export const VISIT = `/api/v1/visits/${VISIT_ID}`;
export const RX = `/api/v1/prescriptions/${RX_ID}`;

export const doctorMember = membership(CLINIC_A, "Alpha Clinic", "DOCTOR", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "QUEUE_MOVE", "CLINICAL_VIEW", "CLINICAL_WRITE", "RX_PRINT"],
});

export function visit(overrides: Partial<Visit> = {}): Visit {
  return {
    id: VISIT_ID,
    patient_id: patient().id,
    doctor_id: DOCTOR_ID,
    appointment_id: "0192f0a0-0000-7000-8000-0000000000f1",
    status: "OPEN",
    chief_complaint: null,
    findings: null,
    diagnosis: null,
    notes: null,
    vitals: {},
    revision: 1,
    started_at: "2026-10-18T04:30:00+00:00",
    completed_at: null,
    locked_at: null,
    is_locked: false,
    addenda: [],
    created_at: "2026-10-18T04:30:00+00:00",
    updated_at: "2026-10-18T04:30:00+00:00",
    ...overrides,
  };
}

export const earlier: VisitSummary = {
  id: EARLIER_ID,
  doctor_id: DOCTOR_ID,
  appointment_id: "0192f0a0-0000-7000-8000-0000000000f0",
  status: "COMPLETED",
  started_at: "2026-09-02T05:00:00+00:00",
  completed_at: "2026-09-02T05:20:00+00:00",
  chief_complaint: "Earlier complaint",
  diagnosis: "Earlier diagnosis",
  prescription: {
    id: "0192f0a0-0000-7000-8000-0000000003a0",
    version: 1,
    issued_at: "2026-09-02T05:15:00+00:00",
    items: [{ medicine_name: "Tablet Sample", dose: "1", frequency: "1-0-1", frequency_text: null, timing: "AFTER_FOOD", duration_days: 3 }],
  },
};

export function rx(overrides: Partial<Prescription> = {}): Prescription {
  return {
    id: RX_ID,
    visit_id: VISIT_ID,
    patient_id: patient().id,
    doctor_id: DOCTOR_ID,
    version: 1,
    supersedes_id: null,
    status: "DRAFT",
    revision: 1,
    items: [],
    advice: { diet: [], activity: [], return_if: [], notes: null },
    follow_up_date: null,
    language: null,
    issued_at: null,
    doctor_snapshot: null,
    clinic_snapshot: null,
    link_delivery: null,
    template_id: null,
    versions: [],
    created_at: "2026-10-18T04:35:00+00:00",
    updated_at: "2026-10-18T04:35:00+00:00",
    ...overrides,
  };
}

export const syrupLine = {
  id: "0192f0a0-0000-7000-8000-0000000005c1",
  position: 1,
  medicine_name: "Syrup X",
  form: null,
  strength: null,
  dose: "5 ml",
  frequency: "1-0-1" as const,
  frequency_text: null,
  timing: "AFTER_FOOD" as const,
  duration_days: 5,
  quantity: null,
  preparation: [{ code: "SHAKE_WELL", text: null }],
  storage: [],
  warnings: null,
  notes: null,
};

export function consultation(overrides: Partial<Consultation> = {}): Consultation {
  return { visit: visit(), patient: patient(), history: [earlier], prescriptions: [], ...overrides };
}

export function page(language: "en" | "hi" = "en"): PatientPage {
  return {
    language,
    version: 1,
    clinic_name: "Alpha Clinic",
    clinic_phone_e164: null,
    call_label: language === "en" ? "Call the clinic" : "क्लिनिक को फ़ोन करें",
    doctor_name: "Dr Meera Iyer",
    doctor_lines: ["MBBS"],
    issued_on: { label: language === "en" ? "Date" : "तारीख", value: "18 Oct 2026" },
    updated_note: null,
    medicines_heading: language === "en" ? "Medicines" : "दवाइयाँ",
    medicines: [
      {
        number: 1,
        name: "Syrup X",
        form_strength: null,
        fields: [{ label: language === "en" ? "How to give" : "कैसे दें", value: language === "en" ? "Mix in 10 ml of water" : "10 ml पानी में मिलाएँ" }],
      },
    ],
    advice_heading: "Advice",
    advice: [],
    advice_notes: null,
    follow_up: null,
  };
}

/** The routes the screen needs for the visit's own doctor ("u-1" is the signed-in person). */
export function screenRoutes(c: Consultation = consultation()) {
  return {
    ...workspaceRoutes,
    "GET /api/v1/me": () => json(200, person([doctorMember])),
    "GET /api/v1/clinic/doctors": () => json(200, { items: [doctor({ user_id: "u-1" })] }),
    [`GET ${VISIT}`]: () => json(200, c),
    "GET /api/v1/rx-favourites": () => json(200, { items: [] }),
    "GET /api/v1/rx-templates": () => json(200, { items: [] }),
  };
}
