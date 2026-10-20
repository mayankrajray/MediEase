/**
 * Setup for the queue journeys (M3-P5): a session of the sample doctor running now, and a fresh
 * synthetic patient, made through the API as the seeded owner and front desk. The queue only
 * moves on the session's day and the seeded hours are 10:00–13:00, so a journey that relied on
 * them would fail outside clinic hours; this makes the journeys pass at any time of day.
 */

import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const PASSWORD = process.env.E2E_PASSWORD ?? "MediEase-demo-2026";
export const DESK = "desk@sample-clinic.example";
export const OWNER = "owner@sample-clinic.example";
export const DOCTOR = "doctor@sample-clinic.example";
const ZONE = "Asia/Kolkata";

/** Where a clinic member lands after signing in (M6-P1, decision 6A), or the clinic chooser. */
export const LANDING = /\/(today|select-clinic)$/;

/**
 * Signs in through the form and lands on Today, choosing the first sample clinic when the person
 * works in both (the seeded doctor does).
 */
export async function signInAs(page: Page, email: string): Promise<void> {
  await page.goto("/sign-in");
  await page.getByLabel("Email or phone number").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(LANDING);
  if (page.url().endsWith("/select-clinic")) {
    await page.getByRole("button", { name: /^Sample Clinic\b(?! Two)/ }).click();
  }
  await expect(page).toHaveURL(/\/today$/);
}

/** The queue is one click from anywhere in the workspace: the sidebar's Queue link. */
export async function openQueue(page: Page): Promise<void> {
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Queue" }).click();
  await expect(page).toHaveURL(/\/queue$/);
}

async function csrf(request: APIRequestContext): Promise<string> {
  const state = await request.storageState();
  const cookie = state.cookies.find((c) => c.name === "me_csrf");
  expect(cookie, "signed in").toBeDefined();
  return cookie?.value ?? "";
}

export async function signInApi(request: APIRequestContext, email: string): Promise<string> {
  const resp = await request.post("/api/v1/auth/sign-in", { data: { identifier: email, password: PASSWORD } });
  expect(resp.status()).toBe(200);
  return csrf(request);
}

function wallClock(date: Date): { day: string; time: string } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return { day: `${get("year")}-${get("month")}-${get("day")}`, time: `${get("hour")}:${get("minute")}` };
}

interface Session {
  readonly id: string;
  readonly status: string;
  readonly starts_at: string;
  readonly ends_at: string;
  readonly available: number;
}

/** The doctor's open session with room that is running now, adding an extra one if none is. */
export async function sessionRunningNow(request: APIRequestContext): Promise<{ doctorId: string; sessionId: string }> {
  const token = await signInApi(request, OWNER);
  const doctors = (await (await request.get("/api/v1/clinic/doctors")).json()) as { items: { id: string }[] };
  const doctorId = doctors.items[0]?.id ?? "";
  const now = Date.now();
  const today = wallClock(new Date(now)).day;

  const running = async () => {
    const list = (await (await request.get(`/api/v1/sessions?date=${today}&doctor_id=${doctorId}`)).json()) as {
      items: Session[];
    };
    return list.items.find(
      (s) => s.status === "OPEN" && s.available > 0 && Date.parse(s.starts_at) <= now && Date.parse(s.ends_at) > now + 120_000,
    );
  };

  const found = await running();
  if (found !== undefined) return { doctorId, sessionId: found.id };

  const start = new Date(now - 5 * 60_000);
  start.setUTCSeconds(0, 0);
  start.setUTCMinutes(start.getUTCMinutes() - (start.getUTCMinutes() % 5));
  const from = wallClock(start);
  const to = wallClock(new Date(start.getTime() + 45 * 60_000));
  const added = await request.post(`/api/v1/clinic/doctors/${doctorId}/schedule-exceptions`, {
    headers: { "X-CSRF-Token": token },
    data: { kind: "EXTRA", on_date: from.day, start_time: from.time, end_time: to.time, slot_minutes: 15, capacity: 30, note: "e2e" },
  });
  expect(added.status(), await added.text()).toBe(201);
  const made = await running();
  expect(made, "the extra session is listed").toBeDefined();
  return { doctorId, sessionId: made?.id ?? "" };
}

/** A new synthetic family member on the Rao family's phone, with a unique name. */
export async function newPatient(request: APIRequestContext, label: string): Promise<{ id: string; name: string }> {
  const token = await signInApi(request, DESK);
  const name = `${label} Rao ${Date.now().toString(36)}`;
  const resp = await request.post("/api/v1/patients", {
    headers: { "X-CSRF-Token": token },
    data: { full_name: name, phone: "9000000101", sex: "FEMALE", date_of_birth: "1991-02-03", confirm_new: true },
  });
  expect(resp.status(), await resp.text()).toBe(201);
  return { id: ((await resp.json()) as { id: string }).id, name };
}
