import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";

import { expectAccessible, firstLoadBytes, issuedLink, noHorizontalScroll, signInWithGoogle } from "./portal-support";

/**
 * M6b-P3 (FR-REM-03; patient portal R28-R44, AC13-AC17) at 360 px: the doctor wrote Tab Sample
 * 1-1-0 after food for 5 days, with water, and Syrup Sample SOS. The linked patient sees Morning and
 * Afternoon with "Day 1 of 5", the syrup "As the doctor wrote", the safety line and the call; sets a
 * 07:30 morning reminder that is still there after a reload; the plan in Hindi; the slot times under
 * Account. Every planner screen is checked for weight (< 200 KB), overflow and axe.
 */

test.use({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });

const BUDGET = 200 * 1024;

const LINES = [
  {
    medicine_name: "Tab Sample",
    dose: "1 tablet",
    frequency: "1-1-0",
    timing: "AFTER_FOOD",
    duration_kind: "DAYS",
    duration_days: 5,
    preparation: [{ code: "WITH_WATER" }],
  },
  { medicine_name: "Syrup Sample", dose: "5 ml", frequency: "SOS", duration_kind: "ONGOING" },
];

/**
 * Chooses a time as the browser's own picker would. `fill` on a time input sets `value` through the
 * element, which React's change tracking does not count as an edit; the prototype's setter does.
 */
async function setTime(input: Locator, value: string) {
  await input.evaluate((el, v) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(el, v);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, value);
  await expect(input).toHaveValue(value);
}

async function checkScreen(page: Page, browser: Browser, heading: string) {
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  await noHorizontalScroll(page);
  await expectAccessible(page);
  const path = new URL(page.url()).pathname;
  const bytes = await firstLoadBytes(browser, page, path, async (p) => {
    await expect(p.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  });
  console.log(`NFR-02 ${path}: ${bytes} bytes`);
  expect(bytes, `NFR-02: ${path} under 200 KB`).toBeLessThan(BUDGET);
}

test("M6b-P3: the medicine plan lays out the prescription, and a reminder choice is kept", async ({ page, browser, request }) => {
  test.setTimeout(180_000);
  const email = `nisha.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`;
  await signInWithGoogle(page, email);
  const rxPath = await issuedLink(request, LINES);
  await page.goto(`/portal/link/prescription/${rxPath.replace("/p/", "")}`);
  await page.getByLabel("Last 4 digits of your phone number").fill("0101");
  await page.getByRole("button", { name: "Save to my MediEase" }).click();
  await expect(page.getByRole("heading", { name: "Linked" })).toBeVisible();

  // AC13: Today by time of day, as written, the safety line and the call (R36, R37).
  await page.getByRole("navigation", { name: "Patient app" }).getByRole("link", { name: "Medicines" }).click();
  const morning = page.getByRole("region", { name: "Morning · 08:00" });
  await expect(morning).toContainText("Tab Sample");
  await expect(morning).toContainText("After food · Take with water");
  await expect(morning).toContainText("Day 1 of 5");
  await expect(page.getByRole("region", { name: "Afternoon · 14:00" })).toContainText("Tab Sample");
  await expect(page.getByRole("region", { name: /^Night/ })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "As the doctor wrote" })).toContainText("Only when needed");
  await expect(page.getByText("This plan only lays out your prescription. If anything is unclear, ask your doctor.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Contact your clinic" })).toHaveAttribute("href", /^tel:/);
  await checkScreen(page, browser, "My medicines");

  // AC15: a 07:30 morning reminder, saved and still there after a reload (R38).
  await page.getByRole("button", { name: "Courses" }).click();
  await page.getByRole("checkbox", { name: "Remind me · Morning (08:00)" }).check();
  await expect(page.getByText("Your reminder choice is saved.")).toBeVisible();
  const time = page.getByLabel("Reminder time, Morning");
  await setTime(time, "07:30");
  const saved = page.waitForResponse((r) => r.url().endsWith("/api/v1/portal/medicine-plan/reminders") && r.request().method() === "PUT");
  await page.getByRole("button", { name: "Save time" }).click();
  expect((await saved).status()).toBe(200);
  await expect(page.getByRole("button", { name: "Save time" })).toHaveCount(0);
  await noHorizontalScroll(page);
  await expectAccessible(page);
  await page.reload();
  await page.getByRole("button", { name: "Courses" }).click();
  await expect(page.getByRole("checkbox", { name: "Remind me · Morning (08:00)" })).toBeChecked();
  await expect(page.getByLabel("Reminder time, Morning")).toHaveValue("07:30");
  await expect(page.getByRole("checkbox", { name: "Remind me · Afternoon (14:00)" })).not.toBeChecked();
  await page.getByRole("button", { name: "Today" }).click();
  await expect(page.getByRole("region", { name: "Morning · 08:00" })).toContainText("Reminder on at 07:30");

  // AC14: the slot times under Account (R34).
  await page.getByRole("navigation", { name: "Patient app" }).getByRole("link", { name: "Account" }).click();
  await expect(page.getByRole("region", { name: "Your times of day" })).toBeVisible();
  await expect(page.getByLabel("Morning")).toHaveValue("08:00");
  await checkScreen(page, browser, "Account");

  // R42: the planner in Hindi; the medicine as the doctor wrote it.
  await page.getByRole("button", { name: /view in Hindi/ }).click();
  await page.getByRole("navigation", { name: "मरीज़ ऐप" }).getByRole("link", { name: "दवाइयाँ" }).click();
  await expect(page.getByRole("region", { name: "सुबह · 08:00" })).toContainText("Tab Sample");
  await expect(page.getByRole("link", { name: "अपने क्लिनिक से संपर्क करें" })).toBeVisible();
  await checkScreen(page, browser, "मेरी दवाइयाँ");
});
