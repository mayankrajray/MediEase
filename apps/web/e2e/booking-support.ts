/**
 * Shared set-up for the booking-request journeys (M6b-P4, P5): a one-place session of the sample
 * doctor a few days ahead at an hour no earlier run used, a fresh synthetic phone number, and the
 * fake Google sign-in that returns to the page that asked for it.
 */

import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { OWNER, signInApi } from "./queue-support";

export const SLUG = "sample-clinic";
export const DOCTOR_NAME = "Dr. Sample Doctor";

export interface Lonely {
  readonly doctorId: string;
  readonly startsAt: string;
  readonly onDate: string;
}

/** A fresh synthetic mobile number each time: the API allows 5 requests a day per number (R15). */
export const phone = (): string => `9${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;

/**
 * A one-place 2-hour token session, 3-12 days ahead (inside the 14-day request horizon), starting
 * on the hour between 05:00 and 21:00 clinic time; an hour an earlier run used (409) is skipped.
 */
export async function lonelySession(request: APIRequestContext): Promise<Lonely> {
  const token = await signInApi(request, OWNER);
  const doctors = (await (await request.get("/api/v1/clinic/doctors")).json()) as { items: { id: string; display_name: string }[] };
  const doctorId = doctors.items.find((d) => d.display_name === DOCTOR_NAME)?.id ?? "";
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const day = new Date(Date.now() + (3 + Math.floor(Math.random() * 10)) * 86_400_000);
    const onDate = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(day);
    const hour = 5 + Math.floor(Math.random() * 17);
    const start = `${String(hour).padStart(2, "0")}:00`;
    const end = `${String(hour + 2).padStart(2, "0")}:00`;
    const added = await request.post(`/api/v1/clinic/doctors/${doctorId}/schedule-exceptions`, {
      headers: { "X-CSRF-Token": token },
      data: { kind: "EXTRA", on_date: onDate, start_time: start, end_time: end, slot_minutes: 120, capacity: 1, note: "e2e" },
    });
    if (added.status() !== 201) continue; // overlaps an earlier run: try another
    const listed = (await (await request.get(`/api/v1/sessions?date=${onDate}&doctor_id=${doctorId}`)).json()) as {
      items: { starts_at: string; capacity: number }[];
    };
    const minutes = (hour * 60 - 330 + 1440) % 1440;
    const mine = listed.items.find((s) => s.capacity === 1 && new Date(s.starts_at).getUTCHours() * 60 + new Date(s.starts_at).getUTCMinutes() === minutes);
    if (mine !== undefined) return { doctorId, startsAt: mine.starts_at, onDate };
  }
  throw new Error("no free evening for the lonely session");
}

/** The request form's address for a session (the same one the clinic page links to). */
export function requestPath(lonely: Lonely): string {
  const query = new URLSearchParams({ clinic: SLUG, doctor: lonely.doctorId, session: lonely.startsAt });
  return `/portal/request?${query.toString()}`;
}

export async function googleSignInThenReturn(page: Page, email: string, expected: RegExp): Promise<void> {
  await page.locator("#portal-email").fill(email);
  await page.getByRole("link", { name: /Continue with Google/ }).click();
  await expect(page).toHaveURL(expected);
}

/** The clinic's clock for a session start, as the staff screens show it ("15:00"). */
export function clinicClock(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
}

/** A new account asks for the session through the request form; returns its phone number. */
export async function askFor(page: Page, lonely: Lonely, label: string): Promise<string> {
  await page.goto(requestPath(lonely));
  await expect(page).toHaveURL(/\/portal\/sign-in\?.*next=/);
  await googleSignInThenReturn(page, `${label}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`, /\/portal\/request\?/);
  const form = page.getByRole("region", { name: "Ask for this time" });
  const number = phone();
  await form.getByLabel(/Phone number/).fill(number);
  await form.getByLabel("This is not an emergency.").check();
  await form.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByRole("region", { name: "Requested" })).toBeVisible();
  return number;
}
