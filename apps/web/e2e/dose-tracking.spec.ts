import { expect, test } from "@playwright/test";

import { expectAccessible, firstLoadBytes, issuedLink, noHorizontalScroll, signInWithGoogle } from "./portal-support";

/**
 * M6b-P3b (patient portal R45-R48, AC19, AC20) at 360 px: the linked patient marks today's morning
 * dose Taken, changes it to Skipped, sees only "contact your clinic" with the call, and finds it in
 * the course's history with counts per state. Weight (< 200 KB), overflow and axe.
 */

test.use({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });

const LINES = [
  { medicine_name: "Tab Sample", dose: "1 tablet", frequency: "1-0-1", duration_kind: "DAYS", duration_days: 5 },
];

test("M6b-P3b: mark a dose, change it, and see it in the history", async ({ page, browser, request }) => {
  test.setTimeout(180_000);
  await signInWithGoogle(page, `ravi.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`);
  const rxPath = await issuedLink(request, LINES);
  await page.goto(`/portal/link/prescription/${rxPath.replace("/p/", "")}`);
  await page.getByLabel("Last 4 digits of your phone number").fill("0101");
  await page.getByRole("button", { name: "Save to my MediEase" }).click();
  await expect(page.getByRole("heading", { name: "Linked" })).toBeVisible();

  await page.getByRole("navigation", { name: "Patient app" }).getByRole("link", { name: "Medicines" }).click();
  const morning = page.getByRole("region", { name: "Morning · 08:00" });
  await morning.getByRole("button", { name: "Taken: Tab Sample, Morning" }).click();
  await expect(morning.getByText(/^Taken at /)).toBeVisible();
  await expect(morning.getByText(/contact your clinic/)).toHaveCount(0);
  await expect(page.getByText("Only you can see what you mark here. Your clinic does not.")).toBeVisible();

  // AC19: changed to Skipped within the window; the only guidance is to contact the clinic.
  await morning.getByRole("button", { name: "Change" }).click();
  await morning.getByRole("button", { name: "Skipped: Tab Sample, Morning" }).click();
  await expect(morning.getByText(/^Skipped at /)).toBeVisible();
  await expect(morning.getByText("If you are unsure what to do, contact your clinic.")).toBeVisible();
  await expect(morning.getByRole("link", { name: "Contact your clinic" })).toHaveAttribute("href", /^tel:/);
  await noHorizontalScroll(page);
  await expectAccessible(page);

  // Kept after a reload, and in the course's history with counts, never a score.
  await page.reload();
  await expect(page.getByRole("region", { name: "Morning · 08:00" }).getByText(/^Skipped at /)).toBeVisible();
  await page.getByRole("button", { name: "Courses" }).click();
  await page.getByRole("button", { name: "History" }).click();
  const history = page.getByRole("region", { name: "History · version 1" });
  await expect(history).toContainText("Skipped 1");
  await expect(history).toContainText(/Morning · Tab Sample \(1 tablet\): Skipped at /);
  await noHorizontalScroll(page);
  await expectAccessible(page);

  const bytes = await firstLoadBytes(browser, page, "/portal/medicines", async (p) => {
    await expect(p.getByRole("heading", { level: 1, name: "My medicines" })).toBeVisible();
  });
  console.log(`NFR-02 /portal/medicines (with marks): ${bytes} bytes`);
  expect(bytes).toBeLessThan(200 * 1024);
});
