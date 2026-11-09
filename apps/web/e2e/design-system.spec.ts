import { expect, test } from "@playwright/test";

import { expectAccessible, noHorizontalScroll } from "./portal-support";

/**
 * M7c-P7 (DESIGN.md): the design-system showcase passes axe (WCAG 2.1 AA, including the retuned
 * colour contrast) at the clinic size and at 360 px, the brand font is served from our origin,
 * and the overlays keep their keyboard behaviour. Sample data only; no sign-in.
 */
for (const viewport of [
  { width: 1366, height: 768 },
  { width: 360, height: 740 },
]) {
  test(`M7c-P7: the design system is accessible at ${viewport.width} px`, async ({ browser }) => {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const fonts: string[] = [];
    page.on("response", (r) => {
      if (r.url().endsWith(".woff2")) fonts.push(r.url());
    });
    await page.goto("/design-system");
    await expect(page.getByRole("heading", { name: "Design system", level: 1 })).toBeVisible();
    await expectAccessible(page);
    await noHorizontalScroll(page);
    const origin = new URL(page.url()).origin;
    expect(fonts.length, "Manrope is loaded").toBeGreaterThan(0);
    expect(fonts.every((url) => url.startsWith(origin)), "fonts come from our origin").toBe(true);
    await context.close();
  });
}

test("M7c-P7: the confirmation dialog starts on the safe choice and Escape keeps everything", async ({ page }) => {
  await page.goto("/design-system");
  await page.getByRole("button", { name: "Cancel appointment" }).click();
  const dialog = page.getByRole("dialog", { name: "Cancel this appointment?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Keep it" })).toBeFocused();
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cancel appointment" })).toBeFocused();
});

test("M7c-P7: a toast is announced and the drawer closes by its button", async ({ page }) => {
  await page.goto("/design-system");
  await page.getByRole("button", { name: "Show a toast" }).click();
  await expect(page.getByText("Appointment booked", { exact: true })).toBeVisible();
  await expect(page.locator('[aria-live="polite"]').filter({ hasText: "Appointment booked" })).toHaveCount(1);
  await page.getByRole("button", { name: "Open a drawer" }).click();
  const drawer = page.getByRole("dialog", { name: "Book an appointment" });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(drawer).toHaveCount(0);
});
