import { expect, test } from "@playwright/test";

import { expectAccessible, noHorizontalScroll } from "./portal-support";

/**
 * M7c-P7 (M1): the landing page's header on a phone (iPhone SE, 375×667) and on a desktop. The
 * developer's review (9 Nov 2026): on a phone the header shows only the logo and Menu, and the open
 * menu covers the screen in front of the hero, with every link reachable without scrolling.
 */
test("M1: on a phone the header is the logo and Menu, and the open menu covers the hero", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 667 } });
  const page = await context.newPage();
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "MediEase" });
  await expect(nav.getByRole("link", { name: "Apply to join", exact: true })).toBeHidden();
  await noHorizontalScroll(page);

  await nav.getByText("Menu", { exact: true }).click();
  const panel = page.locator(".me-menu-panel");
  await expect(panel).toBeVisible();
  const box = await panel.boundingBox();
  expect(box?.height ?? 0, "the menu fills the screen below the bar").toBeGreaterThan(450);

  // Every item is inside the screen and is what is painted there (nothing of the hero above it).
  for (const name of ["For clinics", "For patients", "Pricing", "Staff sign in", "Apply to join MediEase"]) {
    const link = panel.getByRole("link", { name, exact: true });
    await expect(link).toBeInViewport();
    const b = await link.boundingBox();
    const onTop = await page.evaluate(
      ([x, y]) => document.elementFromPoint(x ?? 0, y ?? 0)?.closest(".me-menu-panel") !== null,
      [(b?.x ?? 0) + 10, (b?.y ?? 0) + (b?.height ?? 0) / 2],
    );
    expect(onTop, `${name} is in front`).toBe(true);
  }
  await expectAccessible(page);

  // Choosing a section closes the menu and goes there.
  await panel.getByRole("link", { name: "Pricing", exact: true }).click();
  await expect(panel).toBeHidden();
  await expect(page.getByRole("heading", { name: "Pricing", level: 2 })).toBeInViewport();
  await context.close();
});

test("M1: on a desktop the header carries the links and Apply, and the page passes axe", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "MediEase" });
  await expect(nav.getByRole("link", { name: "Apply to join", exact: true })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Staff sign in" })).toBeVisible();
  await expect(nav.getByText("Menu", { exact: true })).toBeHidden();
  await expectAccessible(page);
});
