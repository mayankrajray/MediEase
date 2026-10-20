/**
 * M6-P1 (decisions 4A, 5A, 6A): the front desk signs in and lands on Today; a patient marked
 * arrived elsewhere raises the Waiting count within one poll (5 s), and the tile opens the queue
 * with that patient waiting. Then the owner's Today at 360 px: the menu drawer instead of the
 * sidebar, no sideways scrolling, and the 7-day tab. Setup as in booking-three-interactions.
 */

import { expect, test } from "@playwright/test";

import { DESK, OWNER, newPatient, sessionRunningNow, signInApi, signInAs } from "./queue-support";

test("M6-P1: sign in, Today, a live count, then the tile opens the queue", async ({ page, request }) => {
  const { sessionId } = await sessionRunningNow(request);
  const patient = await newPatient(request, "Gita");
  const token = await signInApi(request, DESK);
  const booked = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": token },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(booked.status(), await booked.text()).toBe(201);
  const appointment = ((await booked.json()) as { id: string }).id;

  await signInAs(page, DESK);
  await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
  const tiles = page.getByRole("list", { name: "Today's appointments" });
  const waiting = tiles.getByRole("link", { name: /^Waiting/ });
  // The tile reads "Waiting", the number, then its hint ("Arrived, not yet seen").
  const count = async () => Number(/Waiting\s*(\d+)/.exec((await waiting.textContent()) ?? "")?.[1] ?? "NaN");
  const before = await count();
  expect(Number.isInteger(before)).toBe(true);

  const arrived = await request.post(`/api/v1/appointments/${appointment}/transitions`, {
    headers: { "X-CSRF-Token": token },
    data: { from: "BOOKED", to: "ARRIVED" },
  });
  expect(arrived.status(), await arrived.text()).toBe(200);
  await expect(waiting).toContainText(new RegExp(`Waiting\\s*${before + 1}\\s*Arrived`), { timeout: 7_000 });

  await waiting.click();
  await expect(page).toHaveURL(/\/queue$/);
  await expect(page.getByRole("row").filter({ hasText: patient.name })).toContainText("Arrived");
});

test("M6-P1: the owner's Today at 360 px uses the menu drawer and fits the screen", async ({ browser }) => {
  const page = await (await browser.newContext({ viewport: { width: 360, height: 740 } })).newPage();
  await signInAs(page, OWNER);
  await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();

  // No sideways scrolling on a phone.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  // The sidebar is hidden; Menu opens the same links in a drawer.
  await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
  await page.getByRole("banner").getByRole("button", { name: "Menu" }).click();
  const drawer = page.getByRole("dialog", { name: "Menu" });
  await expect(drawer.getByRole("link", { name: "Today" })).toHaveAttribute("aria-current", "page");
  await expect(drawer.getByRole("button", { name: "Sign out" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  // Owners hold USAGE_METRICS_VIEW: the last 7 days are one tab away.
  await page.getByRole("tab", { name: "Last 7 days" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(8);
});
