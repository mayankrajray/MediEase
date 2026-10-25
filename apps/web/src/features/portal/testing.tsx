/** Test helpers for the signed-in portal (M6b-P2). */

import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";

import { json, type Route } from "@/test/api";

import { PortalShell } from "./PortalShell";

export const PORTAL_ACCOUNT = {
  id: "0192f0a0-0000-7000-8000-0000000000e3",
  full_name: "Asha Patient",
  email: "asha.patient@example.test",
  sign_in_method: "PASSWORD",
  email_verified: true,
  language: "en",
  slot_times: { morning: "08:00", afternoon: "14:00", evening: "18:00", night: "21:00" },
} as const;

/** Everything on, email only for the booking answers (spec R62, R63). */
export const PREFERENCES = [
  "booking.accepted",
  "booking.declined",
  "booking.proposed",
  "booking.expired",
  "appointment.confirmed",
  "appointment.moved",
  "appointment.cancelled",
  "prescription.ready",
  "medicine.due",
].map((kind) => ({ kind, in_app: true, email: kind.startsWith("booking.") ? true : null }));

export const CLINIC_ID = "0192f0a0-0000-7000-8000-0000000000e2";
export const OTHER_CLINIC_ID = "0192f0a0-0000-7000-8000-0000000000f2";

export function me(overrides: Record<string, unknown> = {}): Record<string, Route> {
  return {
    "GET /api/v1/portal/me": () => json(200, { account: { ...PORTAL_ACCOUNT, ...overrides } }),
    // M6b-P6: the header's bell asks for its count on every screen.
    "GET /api/v1/portal/notifications/summary": () => json(200, { unread: 0, latest_id: null }, { ETag: '"n0"' }),
    // M6b-P6: the account page's notification switches.
    "GET /api/v1/portal/notification-preferences": () => json(200, { items: PREFERENCES }),
  };
}

export function link(clinicId = CLINIC_ID, name = "Sample Clinic", extra: Record<string, unknown> = {}) {
  return {
    id: `0192f0a0-0000-7000-8000-${clinicId.slice(-12, -2)}e1`,
    clinic: { id: clinicId, name, phone_e164: "+919000000010", address_line: "12 MG Road", city: "Pune", timezone: "Asia/Kolkata" },
    patient_first_name: "Asha",
    patient_code: "SC-0004",
    method: "INVITE",
    linked_at: "2026-10-24T05:30:00Z",
    ...extra,
  };
}

/** Renders a screen inside the portal shell and waits for the shell to load the account. */
export async function renderPortal(ui: ReactElement): Promise<void> {
  render(<PortalShell>{ui}</PortalShell>);
  await screen.findByRole("navigation", {}, { timeout: 5000 });
}
