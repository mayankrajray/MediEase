import { expect, test, type Browser, type Page } from "@playwright/test";

import { DOCTOR_NAME, googleSignInThenReturn, lonelySession, phone, SLUG } from "./booking-support";

import { expectAccessible, firstLoadBytes, noHorizontalScroll } from "./portal-support";
import { DESK, newPatient, openQueue, signInAs } from "./queue-support";

/**
 * M6b-P4 (FR-PUB-01..04, FR-BKG-01, 02, 07, NFR-02, 10, 11, 17; spec booking-requests AC1-AC7):
 * a patient opens the clinic page at 360 px, picks a time, signs in (the page returns to the same
 * time), asks for it, and sees *Requested*; a second account is refused the held time; front desk
 * sees the request and the hold, and books over it only after confirming. An unknown clinic is a
 * plain not-found. Google is the fake provider on the local stack (a verified account).
 *
 * The two request journeys make 3 requests from one address, and the API allows 20 an hour per
 * address (spec R15). That is plenty for one run (and for CI, which starts empty) but a developer
 * re-running the suite many times within an hour will meet "Too many attempts": wait for the hour
 * or clear the buckets (`DELETE FROM public_rate_limits WHERE bucket LIKE 'bkreq-%'`, local only).
 * Each request uses a new phone number (5 a day per number).
 */

const BUDGET = 200 * 1024;

async function checkScreen(page: Page, browser: Browser, heading: string | RegExp, level: 1 | 2 = 1) {
  await expect(page.getByRole("heading", { level, name: heading })).toBeVisible();
  await noHorizontalScroll(page);
  await expectAccessible(page);
  const path = new URL(page.url()).pathname + new URL(page.url()).search;
  const bytes = await firstLoadBytes(browser, page, path, async (p) => {
    await expect(p.getByRole("heading", { level, name: heading })).toBeVisible();
  });
  console.log(`NFR-02 ${path}: ${bytes} bytes`);
  expect(bytes, `NFR-02: ${path} under 200 KB`).toBeLessThan(BUDGET);
}

test.describe("the clinic page and a booking request at 360 px", () => {
  test.use({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });

  test("an unknown clinic is a plain not-found (AC2)", async ({ page }) => {
    const resp = await page.goto("/c/no-such-clinic");
    expect(resp?.status()).toBe(404);
    await expect(page.getByRole("heading", { name: "This page could not be found." })).toBeVisible();
    await expect(page.getByText("no-such-clinic")).toHaveCount(0);
  });

  test("ask for a time, be refused the held one, and see Requested", async ({ page, browser, request }) => {
    test.setTimeout(240_000);
    const lonely = await lonelySession(request);
    const sessionParam = encodeURIComponent(lonely.startsAt);

    // The public page: allow-list content, emergency notice, accessible, light, no sign-in.
    await page.goto(`/c/${SLUG}`);
    await expect(page.getByRole("note")).toContainText("not for emergencies");
    await checkScreen(page, browser, "Sample Clinic");
    await page.getByRole("button", { name: "See times" }).first().click();
    const link = page.locator(`a[href*="session=${sessionParam}"]`).first();
    await expect(link).toBeVisible();
    const requestPath = (await link.getAttribute("href")) ?? "";
    expect(requestPath).toContain("/portal/request?");

    // Choosing the time asks to sign in, and signing in brings the patient back to the same time.
    await link.click();
    await expect(page).toHaveURL(/\/portal\/sign-in\?.*next=/);
    const email = `ritu.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`;
    await googleSignInThenReturn(page, email, /\/portal\/request\?/);
    expect(new URL(page.url()).searchParams.get("session")).toBe(lonely.startsAt);

    // The form: phone only is required; age and sex are optional (the seeded clinic does not ask).
    const form = page.getByRole("region", { name: "Ask for this time" });
    await expect(form).toBeVisible();
    await expect(form.getByLabel(/^Age in years \(optional\)/)).toBeVisible();
    await checkScreen(page, browser, "Ask for this time", 2); // a section title: this page has no h1
    await form.getByLabel(/Phone number/).fill(phone());
    await form.getByLabel("This is not an emergency.").check();
    await form.getByRole("button", { name: "Send request" }).click();
    await expect(page.getByRole("region", { name: "Requested" })).toContainText("clinic will reply");

    // The patient sees it as Requested in My appointments.
    await page.getByRole("link", { name: "Go to My appointments" }).click();
    await expect(page.getByRole("region", { name: "Requested" })).toContainText(DOCTOR_NAME);
    await checkScreen(page, browser, "My appointments");

    // A second account asking for the same, held time is refused in words (AC1, AC4).
    const other = await browser.newContext({ viewport: { width: 360, height: 740 } });
    const second = await other.newPage();
    await second.goto(requestPath);
    await expect(second).toHaveURL(/\/portal\/sign-in\?.*next=/);
    await googleSignInThenReturn(second, `kiran.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`, /\/portal\/request\?/);
    const form2 = second.getByRole("region", { name: "Ask for this time" });
    await form2.getByLabel(/Phone number/).fill(phone());
    await form2.getByLabel("This is not an emergency.").check();
    await form2.getByRole("button", { name: "Send request" }).click();
    await expect(form2.getByRole("alert")).toContainText(/Someone else|holding it|full/);
    await other.close();

    // The clinic page no longer offers the held time (AC4).
    await page.goto(`/c/${SLUG}`);
    await page.getByRole("button", { name: "See times" }).first().click();
    await expect(page.getByRole("heading", { name: /^Free times with/ })).toBeVisible();
    await expect(page.locator(`a[href*="session=${sessionParam}"]`)).toHaveCount(0);
  });
});

test("front desk sees the request and its hold, and books over it only after confirming (AC5, R18a)", async ({ page, browser, request }) => {
  test.setTimeout(240_000);
  const lonely = await lonelySession(request);
  const sessionParam = encodeURIComponent(lonely.startsAt);

  // A patient asks (through the API as the portal would, in a throwaway signed-in context).
  const patientContext = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const patientPage = await patientContext.newPage();
  await patientPage.goto(`/c/${SLUG}`);
  await patientPage.getByRole("button", { name: "See times" }).first().click();
  const link = patientPage.locator(`a[href*="session=${sessionParam}"]`).first();
  await expect(link).toBeVisible();
  await link.click();
  await googleSignInThenReturn(patientPage, `desk.view.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`, /\/portal\/request\?/);
  const form = patientPage.getByRole("region", { name: "Ask for this time" });
  await form.getByLabel(/Phone number/).fill(phone());
  await form.getByLabel("This is not an emergency.").check();
  await form.getByRole("button", { name: "Send request" }).click();
  await expect(patientPage.getByRole("region", { name: "Requested" })).toBeVisible();
  await patientContext.close();

  // Front desk: the request is in the list, with its hold.
  await signInAs(page, DESK);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Booking requests" }).click();
  await expect(page).toHaveURL(/\/booking-requests$/);
  await expect(page.getByRole("table")).toContainText("Held until");
  await expectAccessible(page);

  // The booking drawer shows the time as held; booking it asks first, then books anyway.
  const patient = await newPatient(request, "Override", DESK);
  await openQueue(page);
  await page.getByRole("button", { name: "Book" }).click();
  const drawer = page.getByRole("dialog", { name: "Book appointment" });
  await drawer.getByLabel("Patient").fill(patient.name);
  await drawer.getByRole("button", { name: new RegExp(patient.name) }).click();
  await drawer.getByLabel("Doctor").selectOption({ label: DOCTOR_NAME });
  await drawer.getByLabel("Date").fill(lonely.onDate);
  // Earlier runs may have left other held sessions on this date: pick this one by its start time.
  const startsAtClinic = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(lonely.startsAt));
  const held = drawer.getByRole("radio", { name: new RegExp(`^${startsAtClinic}.*held`, "i") });
  await expect(held).toBeVisible();
  await held.check();
  await drawer.getByRole("button", { name: "Confirm booking" }).click();
  const ask = drawer.getByRole("alertdialog");
  await expect(ask).toContainText("A patient asked for this time online");
  await ask.getByRole("button", { name: /Book anyway/ }).click();
  await expect(page.getByRole("status").filter({ hasText: `${patient.name} booked` })).toBeVisible();

  // The request stays open, but no longer holds the time.
  await page.goto("/booking-requests");
  await expect(page.getByRole("table")).toContainText("Booked over");
});
