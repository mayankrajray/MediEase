import { expect, test } from "@playwright/test";

import { linkPath, waitForEmail } from "./mailpit";
import { OWNER, signInApi } from "./queue-support";

/**
 * M6a-P4 (FR-AUTH-05, FR-AUTH-08, ADR-0016): emails sent by the worker into Mailpit, links
 * followed in the browser.
 */

const NEW_PASSWORD = "a-brand-new-synthetic-pass";

function uniqueEmail(label: string): string {
  return `${label}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`;
}

test("M6a-P4: a patient confirms their email from the link and the banner goes", async ({ browser, request }) => {
  const context = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const page = await context.newPage();
  const email = uniqueEmail("meera");

  await page.goto("/portal/sign-up");
  await page.getByLabel("Your name").fill("Meera Patient");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("a-synthetic-patient-pass");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("region", { name: "Confirm your email" })).toBeVisible();

  const text = await waitForEmail(request, email, "Confirm your email");
  await page.goto(linkPath(text, "/portal/verify-email"));
  await page.getByRole("button", { name: "Confirm my email" }).click();
  await expect(page.getByRole("status")).toHaveText(/Your email is confirmed/);

  await page.getByRole("link", { name: "Go to your account" }).click();
  await expect(page.getByText("Verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Confirm your email" })).toHaveCount(0);
  await context.close();
});

test("M6a-P4: a staff member resets a forgotten password, and the old session ends", async ({ browser, request }) => {
  // A fresh front-desk member, so the seeded accounts keep the demo password.
  const csrf = await signInApi(request, OWNER);
  const email = uniqueEmail("desk.reset");
  const invited = await request.post("/api/v1/clinic/staff", {
    data: { full_name: "Reset Desk", role: "FRONT_DESK", email },
    headers: { "X-CSRF-Token": csrf },
  });
  expect(invited.status()).toBe(201);
  const token = ((await invited.json()) as { accept_url: string }).accept_url.split("/invite/")[1] ?? "";
  const member = await browser.newContext();
  const accepted = await member.request.post(`/api/v1/auth/invites/${token}/accept`, {
    data: { password: "an-old-synthetic-password" },
  });
  expect(accepted.status()).toBe(200);
  expect((await member.request.get("/api/v1/me")).status()).toBe(200);

  const page = await browser.newPage();
  await page.goto("/sign-in");
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send the link" }).click();
  await expect(page.getByRole("status")).toHaveText(/If an account uses that email/);

  const link = linkPath(await waitForEmail(request, email, "Reset your MediEase password"), "/reset-password");
  await page.goto(link);
  await page.getByLabel(/^New password/).fill(NEW_PASSWORD);
  await page.getByLabel("Type it again").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Save the new password" }).click();
  await expect(page).toHaveURL(/\/sign-in\?reason=password_reset$/);
  await expect(page.getByRole("status")).toHaveText(/Your password was changed/);

  expect((await member.request.get("/api/v1/me")).status()).toBe(401); // every session ended

  await page.getByLabel("Email or phone number").fill(email);
  await page.getByLabel("Password").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/today$/);

  // Failure path: the link works once.
  await page.goto(link);
  await page.getByLabel(/^New password/).fill(NEW_PASSWORD);
  await page.getByLabel("Type it again").fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Save the new password" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /not valid any more/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Ask for a new link" })).toBeVisible();
  await member.close();
});
