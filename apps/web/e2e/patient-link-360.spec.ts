/**
 * M4-P5 (FR-RX-07, 08; spec AC2, AC3, R11, R19, NFR-02): the patient opens their prescription
 * link on a 360-px phone. Setup through the API as the seeded staff: a visit in a session
 * running now, the PRD §8.6 sample issued, the link from the front desk. The synthetic patient's
 * phone ends in 0101 (queue-support.ts).
 */

import { expect, test, type Page } from "@playwright/test";

import { issuedLink } from "./portal-support";

async function noHorizontalScroll(page: Page) {
  const widths = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(widths[0]).toBeLessThanOrEqual(widths[1] ?? 0);
}

test.use({ viewport: { width: 360, height: 640 }, isMobile: true, hasTouch: true });

test("AC2: the sample opens at 360 px after the last-4 check, in English and Hindi", async ({ browser, page, request }) => {
  const path = await issuedLink(request);
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Confirm it is you" })).toBeVisible();
  await expect(page.getByText("Syrup X")).toHaveCount(0); // nothing clinical before the check
  await expect(page).toHaveTitle("Prescription · MediEase"); // R12
  await noHorizontalScroll(page);

  await page.getByLabel("Last 4 digits of your phone number").fill("0000");
  await page.getByRole("button", { name: "Show my prescription" }).click();
  await expect(page.locator("#challenge-problem, main [role=alert]").first()).toContainText("4 tries left");
  await expect(page).not.toHaveURL(/0000/);

  await page.getByLabel("Last 4 digits of your phone number").fill("0101");
  await page.getByRole("button", { name: "Show my prescription" }).click();
  // The medicine card, in the Medicines section (M6b-P3 adds the schedule, which names it too).
  const card = page.getByRole("region", { name: "Medicines" }).getByRole("listitem").filter({ hasText: "Syrup X" });
  await expect(card).toBeVisible();
  const howToGive = card.locator("dt", { hasText: "How to give" });
  await expect(howToGive.locator("xpath=following-sibling::dd[1]")).toContainText("Mix in 10 ml of water"); // AC2
  await expect(card).toContainText("When to take");
  await expect(page.getByRole("link", { name: "Call the clinic" })).toHaveAttribute("href", /^tel:\+91/);
  await noHorizontalScroll(page);
  // NFR-02: a first visit in a fresh browser (nothing cached), bytes on the wire: compressed
  // bodies as sent, plus headers.
  const fresh = await browser.newContext({ storageState: await page.context().storageState(), viewport: { width: 360, height: 640 } });
  const first = await fresh.newPage();
  const transfers: Promise<{ url: string; bytes: number }>[] = [];
  first.on("requestfinished", (req) => {
    transfers.push(
      Promise.all([req.sizes(), req.response()]).then(async ([s, resp]) => {
        const encoded = Number(resp?.headers()["content-length"] ?? Number.NaN);
        const body = s.responseBodySize > 0 ? s.responseBodySize : Number.isFinite(encoded) ? encoded : ((await resp?.body())?.length ?? 0);
        return { url: req.url(), bytes: body + s.responseHeadersSize };
      }),
    );
  });
  await first.goto(path, { waitUntil: "networkidle" });
  await expect(first.getByRole("region", { name: "Medicines" }).getByRole("listitem").filter({ hasText: "Syrup X" })).toBeVisible();
  const loaded = await Promise.all(transfers);
  const total = loaded.reduce((sum, t) => sum + t.bytes, 0);
  console.log(`NFR-02 page weight: ${total} bytes in ${loaded.length} responses`, loaded.map((t) => `${t.bytes} ${new URL(t.url).pathname}`).join("; "));
  await fresh.close();
  expect(total, "NFR-02: under 200 KB for the page and its assets").toBeLessThan(200 * 1024);

  await page.getByRole("link", { name: "हिन्दी में देखें" }).click();
  await expect(page.getByRole("heading", { name: "दवाइयाँ" })).toBeVisible();
  await expect(page.getByRole("region", { name: "दवाइयाँ" }).getByRole("listitem").filter({ hasText: "Syrup X" })).toContainText("कैसे दें");
  await expect(page.getByText("breathing is difficult")).toBeVisible(); // free text as written
  await noHorizontalScroll(page);
});

test("AC3: five wrong answers lock the link, even for the right digits", async ({ page, request }) => {
  const path = await issuedLink(request);
  await page.goto(`${path}?lang=en`);
  for (let i = 0; i < 5; i += 1) {
    await page.getByLabel("Last 4 digits of your phone number").fill("1234");
    await page.getByRole("button", { name: "Show my prescription" }).click();
    await expect(page.locator("#challenge-problem, main [role=alert]").first()).toBeVisible();
  }
  await expect(page.locator("#challenge-problem, main [role=alert]").first()).toContainText("contact the clinic");
  await expect(page.getByLabel("Last 4 digits of your phone number")).toHaveCount(0);
});
