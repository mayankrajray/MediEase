/**
 * Setup for the M6a-P8 journeys: a future weekday where the sample doctor has open sessions on
 * that day and the next, found through the API, so the journeys pass on any day and reruns.
 */

import { expect, type APIRequestContext } from "@playwright/test";

import { DESK, OWNER, newPatient, signInApi } from "./queue-support";

export const DOCTOR_NAME = "Dr. Sample Doctor";

interface Session {
  readonly id: string;
  readonly status: string;
  readonly available: number;
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

/** Letters only, different each run: patient names in these journeys are unique. */
export function uniqueWord(prefix: string): string {
  return prefix + Date.now().toString(26).replace(/[0-9]/g, (digit) => "abcdefghij"[Number(digit)] ?? "a");
}

async function openSessions(request: APIRequestContext, doctorId: string, day: string): Promise<Session[]> {
  const list = (await (await request.get(`/api/v1/sessions?date=${day}&doctor_id=${doctorId}`)).json()) as { items: Session[] };
  return list.items.filter((s) => s.status === "OPEN" && s.available > 0);
}

/** The sample doctor's ID and a day 40-90 days ahead with open sessions that day and the next. */
export async function bookableDays(request: APIRequestContext): Promise<{ doctorId: string; day: string; next: string; sessionId: string }> {
  await signInApi(request, OWNER);
  const doctors = (await (await request.get("/api/v1/clinic/doctors")).json()) as { items: { id: string; display_name: string }[] };
  const doctorId = doctors.items.find((d) => d.display_name === DOCTOR_NAME)?.id ?? "";
  expect(doctorId, "the seeded sample doctor").not.toBe("");
  const start = 40 + Math.floor(Math.random() * 40);
  for (let offset = start; offset < start + 14; offset += 1) {
    const day = iso(new Date(Date.now() + offset * 86_400_000));
    const next = iso(new Date(Date.now() + (offset + 1) * 86_400_000));
    const today = await openSessions(request, doctorId, day);
    if (today.length > 0 && (await openSessions(request, doctorId, next)).length > 0) {
      return { doctorId, day, next, sessionId: today[0]?.id ?? "" };
    }
  }
  throw new Error("no two consecutive days with open sessions for the sample doctor");
}

/** A fresh consenting patient booked into ``sessionId`` by the front desk. */
export async function bookPatient(request: APIRequestContext, label: string, sessionId: string): Promise<{ id: string; first: string }> {
  const patient = await newPatient(request, label);
  const token = await signInApi(request, DESK);
  const consent = await request.put(`/api/v1/patients/${patient.id}/consent`, {
    headers: { "X-CSRF-Token": token },
    data: { whatsapp: true, sms: false },
  });
  expect(consent.status(), await consent.text()).toBe(200);
  const booked = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": token },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(booked.status(), await booked.text()).toBe(201);
  return { id: ((await booked.json()) as { id: string }).id, first: label };
}
