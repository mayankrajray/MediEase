/**
 * M4-P6 (FR-RX-01..06, FR-VIS-02, spec §6, D6, NFR-09): at 1366 × 768 the doctor starts the
 * consultation from the queue, writes notes and types the PRD §8.6 sample with the keyboard,
 * issues it after the preview, sees the QR link and prints; then the front desk sees
 * "Prescription issued" on the row and prints it too. Setup through the API as in
 * queue-two-browsers.spec.ts.
 */

import { readFile } from "node:fs/promises";

import { expect, test, type Browser, type Download, type Page } from "@playwright/test";

import { DESK, DOCTOR, newPatient, openQueue, sessionRunningNow, signInApi, signInAs } from "./queue-support";

test.use({ viewport: { width: 1366, height: 768 } });

async function boardAs(browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 768 } })).newPage();
  // M6-P1: every member lands on Today; the queue is one click away.
  await signInAs(page, email);
  await openQueue(page);
  return page;
}

/** Every form control on the page has an accessible name (labels, not placeholders). */
async function everyFieldLabelled(page: Page) {
  const unlabelled = await page.evaluate(() =>
    [...document.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>("main input, main select, main textarea")]
      .filter((el) => el.type !== "hidden" && (el.labels?.length ?? 0) === 0 && !el.getAttribute("aria-label"))
      .map((el) => el.outerHTML.slice(0, 80)),
  );
  expect(unlabelled).toEqual([]);
}

/**
 * Print opens a tab at the click and points it at the PDF (a blob: URL). Headless Chromium has no
 * PDF viewer, so there the PDF arrives as a download of that URL instead; either way it must be
 * a real PDF.
 */
async function opensPdf(page: Page, open: () => Promise<void>) {
  // Listen from the moment the tab exists: a PDF already stored arrives within milliseconds.
  const download = new Promise<Download>((resolve) => {
    page.context().once("page", (tab) => void tab.waitForEvent("download", { timeout: 15_000 }).then(resolve));
  });
  const popup = page.waitForEvent("popup");
  await open();
  const tab = await popup;
  const file = await download;
  expect(file.url()).toMatch(/^blob:/);
  const bytes = await readFile(await file.path());
  expect(bytes.subarray(0, 5).toString("latin1")).toBe("%PDF-");
  await tab.close();
}

test("the doctor writes and issues the sample with the keyboard; the front desk prints it", async ({ browser, request }) => {
  test.setTimeout(120_000);
  const { sessionId } = await sessionRunningNow(request);
  const patient = await newPatient(request, "Kavya");
  const token = await signInApi(request, DESK);
  const booked = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": token },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(booked.status(), await booked.text()).toBe(201);
  const appointment = ((await booked.json()) as { id: string }).id;
  const arrived = await request.post(`/api/v1/appointments/${appointment}/transitions`, {
    headers: { "X-CSRF-Token": token },
    data: { from: "BOOKED", to: "ARRIVED" },
  });
  expect(arrived.status(), await arrived.text()).toBe(200);

  // Journey 1: Start on the doctor's own row opens the consultation.
  const doctor = await boardAs(browser, DOCTOR);
  await doctor.getByRole("button", { name: `Start ${patient.name}'s consultation` }).click();
  await expect(doctor).toHaveURL(/\/visits\/[0-9a-f-]{36}$/);
  await expect(doctor).toHaveTitle("Consultation · MediEase"); // never the patient's name
  await expect(doctor.getByRole("heading", { level: 1 })).toHaveText(patient.name);
  await expect(doctor.getByText("This is the first visit.")).toBeVisible();
  await everyFieldLabelled(doctor);

  // Notes, saved as typed.
  await doctor.getByLabel("Chief complaint").focus();
  await doctor.keyboard.type("Cough for 3 days");
  await doctor.keyboard.press("Tab");
  await expect(doctor.getByRole("region", { name: "Notes" }).getByRole("status")).toHaveText("Saved");

  // Journey 3: medicine, Tab, dose, Tab, frequency, Tab, timing, Tab, days, Enter.
  const medicine = doctor.getByRole("combobox", { name: "Medicine" });
  await medicine.focus();
  await doctor.keyboard.type("Syrup X");
  await doctor.keyboard.press("Tab");
  await expect(doctor.getByLabel("Dose")).toBeFocused();
  await doctor.keyboard.type("5 ml");
  await doctor.keyboard.press("Tab");
  // M6b-P3 (prescriptions R21), failure path: all zeros is not a pattern; it is refused on the field.
  await doctor.keyboard.type("000");
  await expect(doctor.getByLabel("Frequency")).toHaveAttribute("aria-invalid", "true");
  for (let i = 0; i < 3; i++) await doctor.keyboard.press("Backspace");
  await doctor.keyboard.type("101");
  await expect(doctor.getByText("1-0-1 · morning and night")).toBeVisible();
  await doctor.keyboard.press("Tab");
  await expect(doctor.getByLabel("Timing")).toBeFocused();
  await doctor.keyboard.press("ArrowDown"); // the first choice: After food
  await expect(doctor.getByLabel("Timing")).toHaveValue("AFTER_FOOD");
  await doctor.keyboard.press("Tab");
  await doctor.keyboard.type("5");
  await doctor.keyboard.press("Enter");
  const lines = doctor.getByRole("list", { name: "Medicines" });
  await expect(lines).toContainText("1. Syrup X · 5 ml · 1-0-1 · after food · 5 days");
  await expect(medicine).toBeFocused();

  // More: the patient instructions of the sample, still from the keyboard.
  await doctor.getByRole("button", { name: "More for line 1, Syrup X" }).focus();
  await doctor.keyboard.press("Enter");
  const drawer = doctor.getByRole("dialog", { name: "Line 1: Syrup X" });
  await drawer.getByLabel("Shake well").focus();
  await doctor.keyboard.press("Space");
  await drawer.getByLabel("Mix in water").focus();
  await doctor.keyboard.press("Space");
  await drawer.getByLabel("Amount of water, e.g. 10 ml").focus();
  await doctor.keyboard.type("10 ml");
  await drawer.getByRole("button", { name: "Done" }).focus();
  await doctor.keyboard.press("Enter");
  await expect(drawer).toHaveCount(0);
  await expect(lines).toContainText("with instructions");
  await expect(doctor.getByRole("region", { name: /^Prescription/ }).getByRole("status").last()).toContainText("Saved", { timeout: 10_000 });

  // Verify step 2: reloading keeps the draft.
  await doctor.reload();
  await expect(doctor.getByRole("list", { name: "Medicines" })).toContainText("Syrup X · 5 ml · 1-0-1 · after food · 5 days");
  await expect(doctor.getByLabel("Chief complaint")).toHaveValue("Cough for 3 days");

  // Journey 4: the preview is the patient's own page; then Hindi; then Issue.
  await doctor.getByRole("button", { name: "Review and issue" }).click();
  const review = doctor.getByRole("dialog", { name: "Review and issue" });
  const preview = review.getByRole("region", { name: "What the patient will see" });
  const howToGive = preview.locator("dt", { hasText: "How to give" });
  await expect(howToGive.locator("xpath=following-sibling::dd[1]")).toContainText("Mix in 10 ml of water");
  await review.getByRole("button", { name: "हिन्दी (Hindi)" }).click();
  await expect(preview).toHaveAttribute("lang", "hi");
  await expect(preview).toContainText("कैसे दें");
  await review.getByRole("button", { name: "Issue" }).click();
  await expect(doctor.getByRole("heading", { name: "Prescription issued" })).toBeVisible();
  await expect(doctor.getByRole("img", { name: /QR code/ })).toBeVisible();
  await expect(doctor.getByTestId("patient-link")).toContainText("/p/");
  await opensPdf(doctor, () => doctor.getByRole("button", { name: "Print the prescription" }).click());

  // Journey 5: Complete returns to the queue, where the row is completed.
  await doctor.getByRole("button", { name: "Complete visit" }).click();
  await expect(doctor).toHaveURL(/\/queue$/);
  await expect(doctor.getByRole("row").filter({ hasText: patient.name })).toContainText("Completed");

  // Journey 6 (spec D6): the front desk sees the state, prints, and sees no clinical content.
  const desk = await boardAs(browser, DESK);
  const row = desk.getByRole("row").filter({ hasText: patient.name });
  await expect(row).toContainText("Prescription issued");
  await expect(row).not.toContainText("Syrup X");
  await row.getByRole("button", { name: `More actions for ${patient.name}` }).click();
  await opensPdf(desk, () => desk.getByRole("menuitem", { name: "Print prescription" }).click());
});

test("verify step 5: a draft changed in a second tab stops the first one saving and offers Reload", async ({ browser, request }) => {
  test.setTimeout(90_000);
  const { sessionId } = await sessionRunningNow(request);
  const patient = await newPatient(request, "Tara");
  const token = await signInApi(request, DESK);
  const booked = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": token },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(booked.status(), await booked.text()).toBe(201);
  const appointment = ((await booked.json()) as { id: string }).id;
  const arrived = await request.post(`/api/v1/appointments/${appointment}/transitions`, {
    headers: { "X-CSRF-Token": token },
    data: { from: "BOOKED", to: "ARRIVED" },
  });
  expect(arrived.status(), await arrived.text()).toBe(200);

  const first = await boardAs(browser, DOCTOR);
  await first.getByRole("button", { name: `Start ${patient.name}'s consultation` }).click();
  await expect(first).toHaveURL(/\/visits\/[0-9a-f-]{36}$/);
  const add = async (page: Page, name: string) => {
    await page.getByRole("combobox", { name: "Medicine" }).fill(name);
    await page.getByRole("combobox", { name: "Medicine" }).press("Enter");
    await expect(page.getByRole("region", { name: /^Prescription/ }).getByRole("status").last()).toContainText("Saved", { timeout: 10_000 });
  };
  await add(first, "Tablet One");

  const second = await first.context().newPage();
  await second.goto(first.url());
  await expect(second.getByRole("list", { name: "Medicines" })).toContainText("Tablet One");
  await add(second, "Tablet Two");

  await first.getByRole("combobox", { name: "Medicine" }).fill("Tablet Three");
  await first.getByRole("combobox", { name: "Medicine" }).press("Enter");
  const banner = first.getByRole("region", { name: /^Prescription/ }).getByRole("alert");
  await expect(banner).toContainText("Changed in another tab", { timeout: 10_000 });
  await banner.getByRole("button", { name: "Reload" }).click();
  const lines = first.getByRole("list", { name: "Medicines" });
  await expect(lines).toContainText("Tablet Two");
  await expect(lines).not.toContainText("Tablet Three");
});
