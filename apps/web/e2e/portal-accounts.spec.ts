import { expect, test } from "@playwright/test";

import { DOCTOR } from "./queue-support";

/**
 * M6a-P3 (FR-AUTH-07, FR-PRT-01, ADR-0015): patient accounts apart from staff, and Google
 * sign-in through the API. On the local stack Google is the fake provider
 * (GOOGLE_OIDC_PROVIDER=fake), which signs in the email typed before "Continue with Google".
 */

const PASSWORD = "a-synthetic-patient-pass";

function uniqueEmail(label: string): string {
  return `${label}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`;
}

test("M6a-P3: a patient signs up by email at 360 px, sees their account and signs out", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const page = await context.newPage();
  const email = uniqueEmail("asha");

  // A signed-out visitor to the portal goes to the portal's own sign-in, not the staff one.
  await page.goto("/portal");
  await expect(page).toHaveURL(/\/portal\/sign-in$/);
  await page.getByRole("link", { name: "Create an account" }).click();
  await expect(page).toHaveURL(/\/portal\/sign-up/);

  await page.getByLabel("Your name").fill("Asha Patient");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/portal$/);
  await expect(page.getByRole("heading", { name: "Hello, Asha Patient" })).toBeVisible();
  await expect(page.getByText("Email and password")).toBeVisible();
  await expect(page.getByRole("region", { name: "No clinic linked yet" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);

  // The portal session opens no staff page.
  await page.goto("/today");
  await expect(page).toHaveURL(/\/sign-in\?next=%2Ftoday$/);

  await page.goto("/portal");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/portal\/sign-in$/);
  await page.goto("/portal");
  await expect(page).toHaveURL(/\/portal\/sign-in$/);

  // And back in with the password.
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Hello, Asha Patient" })).toBeVisible();
  await context.close();
});

test("M6a-P3: a patient signs in with Google (fake provider) and gets a verified account", async ({ page }) => {
  const email = uniqueEmail("ravi.kumar");
  await page.goto("/portal/sign-in");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("link", { name: /Continue with Google/ }).click();

  await expect(page).toHaveURL(/\/portal$/);
  await expect(page.getByRole("heading", { name: /^Hello, Ravi/ })).toBeVisible();
  await expect(page.getByText("Google", { exact: true })).toBeVisible();
  await expect(page.getByText("Verified", { exact: true })).toBeVisible();
});

test("M6a-P3: the seeded doctor uses Continue with Google and lands on Today", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email or phone number").fill(DOCTOR);
  await page.getByRole("link", { name: /Continue with Google/ }).click();

  await expect(page).toHaveURL(/\/(today|select-clinic)/);
  if (new URL(page.url()).pathname === "/select-clinic") {
    await page.getByRole("button", { name: /^Sample Clinic\b(?! Two)/ }).click();
  }
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
});

test("M6a-P3 failure path: an unknown Google address on the staff page is told so", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email or phone number").fill(uniqueEmail("stranger"));
  await page.getByRole("link", { name: /Continue with Google/ }).click();

  await expect(page).toHaveURL(/\/sign-in\?reason=google_no_account$/);
  await expect(page.getByRole("status")).toHaveText(/No MediEase staff account uses this Google address/);
});
