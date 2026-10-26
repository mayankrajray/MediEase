import { expect, test, type Browser, type Page } from "@playwright/test";

import { DOCTOR_NAME, googleSignInThenReturn, phone, SLUG } from "./booking-support";
import { expectAccessible, firstLoadBytes, noHorizontalScroll } from "./portal-support";

/**
 * M6c-P5..P8 (FR-LND-01..03, FR-DIS-01..08; spec discovery AC1, AC5, AC6): a signed-out visitor at
 * 360 px lands on `/`, goes to *Find a doctor*, finds the seeded sample doctor (the seed verifies
 * and lists the demo clinics), opens the profile from the result, picks a time, signs in with the
 * fake Google and asks for it. Failure paths: a search with a bad PIN says so; an unknown profile is
 * a plain not-found.
 */

const BUDGET = 200 * 1024;

async function light(browser: Browser, page: Page, heading: string | RegExp): Promise<void> {
  await noHorizontalScroll(page);
  await expectAccessible(page);
  const url = new URL(page.url());
  const bytes = await firstLoadBytes(browser, page, url.pathname + url.search, async (p) => {
    await expect(p.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  });
  console.log(`NFR-02 ${url.pathname}${url.search}: ${bytes} bytes`);
  expect(bytes, `${url.pathname} under 200 KB`).toBeLessThan(BUDGET);
}

test.describe("discovery at 360 px", () => {
  test.use({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });

  test("the landing page leads to search, a profile, a time and a request", async ({ page, browser }) => {
    test.setTimeout(240_000);

    // P8: the landing page, indexable, light, both paths.
    await page.goto("/");
    const h1 = page.getByRole("heading", { level: 1 });
    await expect(h1).toBeVisible();
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /index, follow/);
    await expect(page.getByRole("link", { name: "Apply to join MediEase" }).first()).toHaveAttribute("href", "/apply");
    await light(browser, page, (await h1.textContent()) ?? "");
    const lcp = await page.evaluate(
      () =>
        new Promise<number>((resolve) => {
          new PerformanceObserver((list) => {
            const entries = list.getEntries();
            resolve(entries[entries.length - 1]?.startTime ?? 0);
          }).observe({ type: "largest-contentful-paint", buffered: true });
          setTimeout(() => resolve(-1), 3000);
        }),
    );
    console.log(`FR-LND-03 LCP (local, no throttling): ${lcp} ms`);
    await page.getByRole("link", { name: "Find a doctor" }).first().click();

    // P6: search the directory.
    await expect(page).toHaveURL(/\/find$/);
    await expect(page.getByRole("heading", { level: 1, name: "Find a doctor" })).toBeVisible();
    await light(browser, page, "Find a doctor");
    await page.getByLabel("Doctor, clinic or specialty").fill("Sample Doctor");
    await page.getByRole("button", { name: "Search" }).click();
    await expect(page).toHaveURL(/q=Sample\+Doctor/);
    const card = page.getByRole("listitem").filter({ hasText: DOCTOR_NAME }).filter({ hasText: "Sample Clinic," }).first();
    await expect(card).toBeVisible();
    await expect(card).toContainText(/Free from|No free time/);
    await expectAccessible(page);

    // P7: the profile from the result carries via=directory to the time and the request form.
    await card.getByRole("link", { name: /See profile and times/ }).click();
    await expect(page).toHaveURL(new RegExp(`/c/${SLUG}/doctors/[0-9a-f-]+\\?via=directory`));
    await expect(page.getByRole("heading", { name: `Free times with ${DOCTOR_NAME}` })).toBeVisible();
    await expect(page.getByRole("link", { name: "All doctors at this clinic" })).toBeVisible();
    await expectAccessible(page);
    const time = page.locator('a[href*="/portal/request?"][href*="via=directory"]').first();
    await expect(time).toBeVisible();
    await time.click();
    await expect(page).toHaveURL(/\/portal\/sign-in\?.*next=/);
    const email = `finder.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`;
    await googleSignInThenReturn(page, email, /\/portal\/request\?.*via=directory/);
    const form = page.getByRole("region", { name: "Ask for this time" });
    await expect(form).toBeVisible();
    await form.getByLabel(/Phone number the clinic can call/).fill(phone());
    await form.getByLabel("This is not an emergency.").check();
    await form.getByRole("button", { name: "Send request" }).click();
    await expect(page.getByRole("heading", { name: "Requested" })).toBeVisible();
  });

  test("a place with nothing says so, and an unknown profile is a plain not-found", async ({ page }) => {
    await page.goto("/find?where=Nowhere%20Town");
    await expect(page.getByText(/Nothing matches yet/)).toBeVisible();
    const resp = await page.goto(`/c/${SLUG}/doctors/0192f0a0-0000-7000-8000-000000000999?via=directory`);
    expect(resp?.status()).toBe(404);
  });
});
