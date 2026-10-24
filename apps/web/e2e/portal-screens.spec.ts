import { expect, test, type Browser, type Page } from "@playwright/test";

import { expectAccessible, firstLoadBytes, issuedLink, noHorizontalScroll } from "./portal-support";

/**
 * M6b-P2 (FR-PRT-03, 04, 05, 07; NFR-02, 10, 11; spec AC7-AC12) at 360 px: a new account's fresh
 * dashboard; after *Save to my MediEase*, Home, Appointments and Prescriptions; Hindi kept on the
 * account; unlinking. Every screen is checked for weight (< 200 KB), overflow and axe.
 * Google is the fake provider on the local stack, which gives a verified account.
 */

test.use({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });

const BUDGET = 200 * 1024;

async function checkScreen(page: Page, browser: Browser, heading: string | RegExp) {
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  await noHorizontalScroll(page);
  await expectAccessible(page);
  const path = new URL(page.url()).pathname + new URL(page.url()).search;
  const bytes = await firstLoadBytes(browser, page, path, async (p) => {
    await expect(p.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  });
  console.log(`NFR-02 ${path}: ${bytes} bytes`);
  expect(bytes, `NFR-02: ${path} under 200 KB`).toBeLessThan(BUDGET);
}

async function signInWithGoogle(page: Page, email: string) {
  await page.goto("/portal/sign-in");
  await page.locator("#portal-email").fill(email);
  await page.getByRole("link", { name: /Continue with Google/ }).click();
  await expect(page).toHaveURL(/\/portal$/);
}

test("M6b-P2: fresh dashboard, linked records, Hindi on the account, and unlinking", async ({ page, browser, request }) => {
  test.setTimeout(180_000);
  const email = `meera.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`;

  // AC7: a new account's fresh dashboard.
  await signInWithGoogle(page, email);
  await expect(page.getByRole("region", { name: "No appointments yet" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Find a doctor" })).toBeVisible();
  await checkScreen(page, browser, /^Hello, Meera/);
  await page.getByRole("link", { name: "Find a doctor" }).click();
  await checkScreen(page, browser, "Find a doctor");

  // Link the records from a prescription link (FR-PRT-06 c).
  const rxPath = await issuedLink(request);
  await page.goto(`/portal/link/prescription/${rxPath.replace("/p/", "")}`);
  await page.getByLabel("Last 4 digits of your phone number").fill("0101");
  await page.getByRole("button", { name: "Save to my MediEase" }).click();
  await expect(page.getByRole("heading", { name: "Linked" })).toBeVisible();

  // Home (R17).
  await page.getByRole("navigation", { name: "Patient app" }).getByRole("link", { name: "Home" }).click();
  await expect(page.getByRole("region", { name: "Next appointment" })).toContainText("Sample Clinic");
  await expect(page.getByRole("region", { name: "Latest prescription" })).toBeVisible();
  await checkScreen(page, browser, /^Hello, Meera/);

  // AC8: My appointments, grouped by clinic, status in words.
  await page.getByRole("navigation", { name: "Patient app" }).getByRole("link", { name: "Appointments" }).click();
  const clinic = page.getByRole("region", { name: "Sample Clinic" });
  await expect(clinic).toContainText("At the clinic");
  await checkScreen(page, browser, "My appointments");

  // AC9: the prescription page and its PDF.
  await page.getByRole("navigation", { name: "Patient app" }).getByRole("link", { name: "Prescriptions" }).click();
  await checkScreen(page, browser, "My prescriptions");
  await page.getByRole("region", { name: "Sample Clinic" }).getByRole("link").first().click();
  await expect(page.getByRole("listitem").filter({ hasText: "Syrup X" })).toBeVisible();
  const prescriptionUrl = page.url();
  await expectAccessible(page);
  await noHorizontalScroll(page);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PDF" }).click();
  expect((await download).suggestedFilename()).toMatch(/^prescription-.*\.pdf$/);

  // AC10: Hindi, saved on the account.
  await page.getByRole("button", { name: /view in Hindi/ }).click();
  await page.getByRole("navigation", { name: "मरीज़ ऐप" }).getByRole("link", { name: "होम" }).click();
  await checkScreen(page, browser, /^नमस्ते, Meera/);
  await page.getByRole("navigation", { name: "मरीज़ ऐप" }).getByRole("link", { name: "अपॉइंटमेंट" }).click();
  await expect(page.getByRole("region", { name: "Sample Clinic" })).toContainText("क्लिनिक में");
  await checkScreen(page, browser, "मेरे अपॉइंटमेंट");
  await page.getByRole("navigation", { name: "मरीज़ ऐप" }).getByRole("link", { name: "खाता" }).click();
  await checkScreen(page, browser, "खाता");
  await page.getByRole("button", { name: "साइन आउट" }).click();
  await expect(page).toHaveURL(/\/portal\/sign-in$/);
  await expect(page.getByRole("heading", { name: "अपने हेल्थ खाते में साइन इन करें" })).toBeVisible();
  await expectAccessible(page);

  // Another browser, signed in again: still Hindi (the account's, not the cookie's).
  const other = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const second = await other.newPage();
  await signInWithGoogle(second, email);
  await expect(second.getByRole("heading", { level: 1, name: /^नमस्ते, Meera/ })).toBeVisible();

  // AC12: unlinking from Account removes the clinic everywhere; failure path: its prescription URL.
  await second.getByRole("navigation", { name: "मरीज़ ऐप" }).getByRole("link", { name: "खाता" }).click();
  await second.getByRole("button", { name: "हटाएँ Sample Clinic" }).click();
  await second.getByRole("button", { name: "हाँ, हटाएँ" }).click();
  await expect(second.getByText("Sample Clinic अब जुड़ा नहीं है।")).toBeVisible();
  await second.goto(new URL(prescriptionUrl).pathname);
  await expect(second.getByRole("main").getByRole("alert")).toContainText("यह नहीं मिला");
  await second.getByRole("navigation", { name: "मरीज़ ऐप" }).getByRole("link", { name: "होम" }).click();
  await expect(second.getByRole("region", { name: "अभी कोई अपॉइंटमेंट नहीं" })).toBeVisible();
  await other.close();
});
