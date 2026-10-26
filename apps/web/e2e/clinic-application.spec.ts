import { expect, test } from "@playwright/test";

import { linkPath, waitForEmail } from "./mailpit";
import { expectAccessible, firstLoadBytes, noHorizontalScroll } from "./portal-support";
import { PASSWORD } from "./queue-support";

/**
 * M6c-P1 (FR-ONB-01, 07; spec clinic-onboarding AC1, AC2, AC4, AC9): a doctor with their own
 * practice applies at 360 px with a PDF certificate, confirms from the email and is thanked with the
 * reply promise; ops sees the application waiting. Failure path: a text file named .pdf is refused
 * on that doctor's step.
 */

test.setTimeout(180_000);

const OPS = "ops@mediease.example";
const PROMISE = "will reply by email within 2 working days";
const PDF = Buffer.from("%PDF-1.4\n% synthetic certificate for the e2e journey\n");

test("AC1, AC2: a solo doctor applies, confirms by email and ops sees it waiting", async ({ browser, page, request }) => {
  const stamp = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
  const email = `apply.${stamp}@example.test`;
  const clinic = `Sample Solo Clinic ${stamp}`;
  // A fresh owner mobile each run: 3 applications a day per phone (R16).
  const mobile = `9${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;

  const context = await browser.newContext({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });
  const phone = await context.newPage();
  await phone.goto("/apply");
  await expect(phone.getByRole("heading", { level: 1, name: "Who is applying" })).toBeVisible();
  await expect(phone.getByText(PROMISE, { exact: false })).toBeVisible();
  await expectAccessible(phone);
  await noHorizontalScroll(phone);
  // NFR-02 (spec clinic-onboarding §6): the form under 200 KB on a first visit.
  const bytes = await firstLoadBytes(browser, phone, "/apply", async (f) => {
    await expect(f.getByRole("heading", { level: 1, name: "Who is applying" })).toBeVisible();
  });
  expect(bytes).toBeLessThan(200 * 1024);

  await phone.getByRole("radio", { name: /A doctor with my own practice/ }).check();
  await phone.getByRole("button", { name: "Next" }).click();
  await phone.getByLabel(/^Clinic name/).fill(clinic);
  await phone.getByLabel(/^Address/).fill("7 Synthetic Lane");
  await phone.getByLabel(/^City/).fill("Pune");
  await phone.getByLabel(/^State/).fill("Maharashtra");
  await phone.getByLabel(/^PIN code/).fill("411001");
  await phone.getByLabel(/^Clinic phone/).fill("9000000124");
  await phone.getByRole("checkbox", { name: "Family Medicine" }).check();
  await phone.getByRole("button", { name: "Next" }).click();
  await phone.getByLabel(/^Owner's full name/).fill("Synthetic Solo Owner");
  await phone.getByLabel(/^Owner's mobile number/).fill(mobile);
  await phone.getByLabel(/^Owner's email/).fill(email);
  await phone.getByRole("button", { name: "Next" }).click();
  await phone.getByLabel(/^Name/).fill("Dr. Synthetic Solo");
  await phone.getByLabel(/^Qualification/).fill("MBBS");
  await phone.getByLabel(/^Medical council/).selectOption("Maharashtra Medical Council");
  await phone.getByLabel(/^Registration number/).fill(`E2E-${stamp}`);
  await expectAccessible(phone);

  // Failure path (AC4): a text file renamed .pdf passes the form's name check but not the API's.
  await phone
    .getByLabel(/^Registration certificate/)
    .setInputFiles({ name: "certificate.pdf", mimeType: "application/pdf", buffer: Buffer.from("plain text, not a PDF") });
  await phone.getByRole("button", { name: "Next" }).click();
  await phone.getByRole("button", { name: "Send application" }).click();
  await expect(phone.getByRole("heading", { level: 1, name: "The doctors" })).toBeVisible();
  await expect(phone.getByRole("alert").filter({ hasText: "Please check" })).toContainText("Use a PDF, JPEG or PNG file.");

  await phone.getByLabel(/^Registration certificate/).setInputFiles({ name: "certificate.pdf", mimeType: "application/pdf", buffer: PDF });
  await phone.getByRole("button", { name: "Next" }).click();
  await phone.getByRole("button", { name: "Send application" }).click();
  await expect(phone.getByRole("heading", { name: "Check your email" })).toBeVisible();
  const status = phone.getByRole("status");
  await expect(status).toContainText("a***@example.test");
  const reference = ((await status.textContent()) ?? "").match(/MA-\d{4}-\d{4,}/)?.[0] ?? "";
  expect(reference).not.toBe("");
  await expect(phone.getByText(PROMISE, { exact: false })).toBeVisible();

  // The confirmation email's link; opening it changes nothing until the button is pressed.
  const link = linkPath(await waitForEmail(request, email, "Confirm your MediEase application"), "/apply/confirm");
  await phone.goto(link);
  await expectAccessible(phone);
  await phone.getByRole("button", { name: "Confirm my application" }).click();
  await expect(phone.getByRole("status")).toContainText(`We received application ${reference}`);
  await expect(phone.getByText(PROMISE, { exact: false })).toBeVisible();
  await noHorizontalScroll(phone);

  // The same link again: one plain answer.
  await phone.goto(link);
  await phone.getByRole("button", { name: "Confirm my application" }).click();
  await expect(phone.getByRole("alert").filter({ hasText: "This link is not valid any more." })).toBeVisible();
  await context.close();

  // Ops sees it waiting (summary only).
  await page.goto("/sign-in");
  await page.getByLabel("Email or phone number").fill(OPS);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/ops$/);
  const waiting = page.getByRole("region", { name: /applications? waiting/ });
  await expect(waiting).toContainText(reference);
  await expect(waiting).toContainText(clinic);
  await expect(waiting).not.toContainText(email);

  // M6c-P2, P3 (AC10, AC11): the reviewer opens it, takes it, checks the doctor and approves.
  await waiting.getByRole("link", { name: reference }).click();
  await expect(page.getByRole("heading", { level: 1, name: new RegExp(reference) })).toBeVisible();
  await expectAccessible(page);
  await page.getByRole("button", { name: "Take for review" }).click();
  await expect(page.getByRole("status").filter({ hasText: "You are reviewing this application." })).toBeVisible();
  const approve = page.getByRole("button", { name: "Approve and create the clinic" });
  await expect(approve).toBeDisabled();
  await page.getByLabel("Found on the council's register").check();
  await page.getByLabel("The certificate matches the application").check();
  await page.getByRole("button", { name: "Mark verified" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Doctor 1 checked." })).toBeVisible();
  await approve.click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Clinic URL name/).fill(`solo-${stamp}`);
  // The dialog fades in (me-overlay); check contrast once it is fully shown.
  await dialog.evaluate((el) => Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished)));
  await expectAccessible(page);
  await dialog.getByRole("button", { name: "Approve and email the owner" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Approved." })).toBeVisible();
  await expect(page.getByText("Approved", { exact: true })).toBeVisible();

  // The owner is invited by email to the confirmed address (R43); the clinic is not public yet (D1).
  await waitForEmail(request, email, "on MediEase");
  const publicPage = await request.get(`/api/v1/public/clinics/solo-${stamp}`);
  expect(publicPage.status()).toBe(404);
});
