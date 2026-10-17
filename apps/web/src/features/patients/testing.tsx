/** Test data for the patient screens: invented people, `+91 90000 00xxx` numbers only. */

import type { ReactNode } from "react";
import { render } from "@testing-library/react";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { WorkspaceGuard } from "@/features/shell/WorkspaceGuard";
import { json } from "@/test/api";

import type { Patient } from "./fields";

export const PATIENT_ID = "0192f0a0-0000-7000-8000-0000000000c1";
export const OTHER_ID = "0192f0a0-0000-7000-8000-0000000000c2";

export const desk = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE"],
});

export function patient(overrides: Partial<Patient> = {}): Patient {
  return {
    id: PATIENT_ID,
    code: "SC-0004",
    full_name: "Bina Shah",
    phone_e164: "+919000000102",
    sex: "FEMALE",
    date_of_birth: null,
    age_years: 47,
    age_is_estimated: true,
    is_minor: false,
    guardian_name: null,
    language: "en",
    whatsapp_consent: false,
    sms_consent: false,
    opted_out: false,
    opted_out_at: null,
    whatsapp_allowed: false,
    sms_allowed: false,
    consent_recorded_at: null,
    consent_recorded_by: null,
    created_at: "2026-10-03T09:00:00+00:00",
    updated_at: "2026-10-03T09:00:00+00:00",
    ...overrides,
  };
}

/** The routes every workspace render needs: who is signed in, and their clinic (Kolkata). */
export const workspaceRoutes = {
  "GET /api/v1/me": () => json(200, person([desk])),
  "GET /api/v1/clinic": () =>
    json(200, {
      id: CLINIC_A,
      name: "Alpha Clinic",
      slug: "alpha",
      timezone: "Asia/Kolkata",
      status: "ACTIVE",
      specialties: [],
      phone_e164: null,
      address_line: null,
      city: null,
      state: null,
      pincode: null,
      patient_code_prefix: "SC",
    }),
};

/** A page inside the real workspace frame: session, clinic gate, shell with search and drawer. */
export function renderInWorkspace(page: ReactNode) {
  return render(
    <SessionProvider>
      <WorkspaceGuard>{page}</WorkspaceGuard>
    </SessionProvider>,
  );
}
