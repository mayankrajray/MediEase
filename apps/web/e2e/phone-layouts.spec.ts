/**
 * M6-P2 (decisions 2A, 3A): the queue, a patient's profile and the follow-ups at 360 px. Each list
 * is a stack of cards with its actions in reach and no sideways scrolling, and the queue still
 * moves a patient from a card. Then reduced motion: a drawer opens without a transition when the
 * system asks for less motion, and with one otherwise. Setup as in booking-three-interactions.
 */

import { expect, test, type Browser, type Page } from "@playwright/test";

import { DESK, newPatient, sessionRunningNow, signInApi, signInAs } from "./queue-support";

const PHONE = { width: 360, height: 740 };

async function noSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function phone(browser: Browser): Promise<Page> {
  const page = await (await browser.newContext({ viewport: PHONE })).newPage();
  await signInAs(page, DESK);
  return page;
}

test("M6-P2: at 360 px the queue is cards, and a card marks its patient arrived", async ({ browser, request }) => {
  const { sessionId } = await sessionRunningNow(request);
  const patient = await newPatient(request, "Hema");
  const token = await signInApi(request, DESK);
  const booked = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": token },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(booked.status(), await booked.text()).toBe(201);

  const page = await phone(browser);
  // The queue is one tap away through the Menu drawer on a phone.
  await page.getByRole("banner").getByRole("button", { name: "Menu" }).click();
  await page.getByRole("dialog", { name: "Menu" }).getByRole("link", { name: "Queue" }).click();
  await expect(page).toHaveURL(/\/queue$/);

  const card = page.getByRole("row").filter({ hasText: patient.name });
  await expect(card).toContainText("Booked");
  // A card, not a table row: as wide as the screen allows, with the column names shown.
  const box = await card.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(280);
  // The column names move into each card; the header row is kept for screen readers only.
  const header = await page.locator("thead").first().boundingBox();
  expect(header?.width ?? 0).toBeLessThanOrEqual(1);
  await noSidewaysScroll(page);

  await card.getByRole("button", { name: `Mark ${patient.name} arrived` }).click();
  await expect(page.getByRole("status").filter({ hasText: `${patient.name} marked arrived` })).toBeVisible();
  await expect(card).toContainText("Arrived");
});

test("M6-P2: at 360 px a patient's profile and the follow-ups fit the screen", async ({ browser, request }) => {
  const patient = await newPatient(request, "Indu");
  const page = await phone(browser);

  await page.goto(`/patients/${patient.id}`);
  await expect(page.getByRole("heading", { level: 1, name: patient.name })).toBeVisible();
  await expect(page.getByRole("button", { name: "Record consent" })).toBeVisible();
  await noSidewaysScroll(page);

  // Recording consent works from the phone layout.
  await page.getByRole("button", { name: "Record consent" }).click();
  await page.getByLabel("WhatsApp: yes").check();
  await page.getByRole("button", { name: "Save answer" }).click();
  await expect(page.getByRole("button", { name: "Change consent" })).toBeVisible();

  await page.goto("/follow-ups");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await noSidewaysScroll(page);
});

test("M6-P2 decision 3A: a drawer slides in, but not when the system asks for less motion", async ({ browser, request }) => {
  await sessionRunningNow(request);
  const duration = async (reducedMotion: "reduce" | "no-preference") => {
    const page = await (await browser.newContext({ reducedMotion })).newPage();
    await signInAs(page, DESK);
    await page.goto("/queue");
    await page.getByRole("button", { name: "Book" }).click();
    const drawer = page.getByRole("dialog", { name: "Book appointment" });
    await expect(drawer).toBeVisible();
    const value = await drawer.evaluate((el) => getComputedStyle(el).transitionDuration);
    await page.context().close();
    return value;
  };
  expect((await duration("reduce")).split(",").every((d) => d.trim() === "0s")).toBe(true);
  expect((await duration("no-preference")).split(",").some((d) => d.trim() !== "0s")).toBe(true);
});
