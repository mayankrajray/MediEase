/**
 * Setup for the queue journeys (M3-P5): a session of the sample doctor running now, and a fresh
 * synthetic patient, made through the API as the seeded owner and front desk. The queue only
 * moves on the session's day and the seeded hours are 10:00–13:00, so a journey that relied on
 * them would fail outside clinic hours; this makes the journeys pass at any time of day.
 */

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

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

/**
 * The doctor's open session with room that is running now, adding an extra one if none is.
 * M6a-P6: `owner` and `doctorName` choose another clinic's owner and one of its doctors.
 */
export async function sessionRunningNow(
  request: APIRequestContext,
  { owner = OWNER, doctorName }: { owner?: string; doctorName?: string } = {},
): Promise<{ doctorId: string; sessionId: string }> {
  const token = await signInApi(request, owner);
  const doctors = (await (await request.get("/api/v1/clinic/doctors")).json()) as {
    items: { id: string; display_name: string }[];
  };
  const doctorId = (doctorName === undefined ? doctors.items[0] : doctors.items.find((d) => d.display_name === doctorName))?.id ?? "";
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

  // An earlier run's extra session may be about to end (under 2 minutes left, so not used) or may
  // have ended in the last 10 minutes. A new one starting up to 10 minutes ago would overlap it
  // (SCH_OVERLAP), so wait for it to end and start the new one no earlier than its end.
  const add = async (notBefore = 0) => {
    const at = Date.now();
    let start = new Date(at - 5 * 60_000);
    start.setUTCSeconds(0, 0);
    start.setUTCMinutes(start.getUTCMinutes() - (start.getUTCMinutes() % 5));
    if (start.getTime() < notBefore) start = new Date(Math.ceil(notBefore / 60_000) * 60_000);
    const from = wallClock(start);
    const to = wallClock(new Date(start.getTime() + 45 * 60_000));
    return request.post(`/api/v1/clinic/doctors/${doctorId}/schedule-exceptions`, {
      headers: { "X-CSRF-Token": token },
      data: { kind: "EXTRA", on_date: from.day, start_time: from.time, end_time: to.time, slot_minutes: 15, capacity: 30, note: "e2e" },
    });
  };
  let added = await add();
  if (added.status() === 409) {
    const today = (await (await request.get(`/api/v1/sessions?date=${wallClock(new Date()).day}&doctor_id=${doctorId}`)).json()) as {
      items: Session[];
    };
    const at = Date.now();
    const recent = today.items.map((s) => Date.parse(s.ends_at)).filter((end) => end > at - 10 * 60_000 && end < at + 130_000);
    // Sessions end on a whole minute, so starting at the last end is never in the future once over.
    const lastEnd = Math.max(0, ...recent);
    const wait = Math.max(0, lastEnd - at) + 2_000;
    test.info().setTimeout(test.info().timeout + wait);
    await new Promise((resolve) => setTimeout(resolve, wait));
    added = await add(lastEnd);
  }
  expect(added.status(), await added.text()).toBe(201);
  const made = await running();
  expect(made, "the extra session is listed").toBeDefined();
  return { doctorId, sessionId: made?.id ?? "" };
}

/** A new synthetic family member on the Rao family's phone, with a unique name. */
export async function newPatient(
  request: APIRequestContext,
  label: string,
  desk: string = DESK,
): Promise<{ id: string; name: string }> {
  const token = await signInApi(request, desk);
  const name = `${label} Rao ${Date.now().toString(36)}`;
  const resp = await request.post("/api/v1/patients", {
    headers: { "X-CSRF-Token": token },
    data: { full_name: name, phone: "9000000101", sex: "FEMALE", date_of_birth: "1991-02-03", confirm_new: true },
  });
  expect(resp.status(), await resp.text()).toBe(201);
  return { id: ((await resp.json()) as { id: string }).id, name };
}
