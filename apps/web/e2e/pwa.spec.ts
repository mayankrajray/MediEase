import { expect, test, type Page } from "@playwright/test";

import { expectAccessible, noHorizontalScroll } from "./portal-support";

/**
 * M7e-E1 (docs/milestones/M7e-pwa-push.md §3 E1, §5): the installable app on the real stack.
 * The manifest and icons are valid, the service worker takes over, a page that cannot load shows
 * the offline page, and no API answer or page is ever served from or stored in its cache.
 *
 * Service workers need a secure origin. Browsers count localhost as one; the journeys reach the
 * app at http://web:3000 on the compose network, so Chromium is told to treat that origin as
 * secure for this file only. The flag needs the full Chromium build (`channel: "chromium"`, in the
 * official Playwright image); the default headless shell ignores it.
 */

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
test.use({ channel: "chromium", launchOptions: { args: [`--unsafely-treat-insecure-origin-as-secure=${new URL(BASE).origin}`] } });

/** The cache's contents as paths, read inside the page. */
async function cachedPaths(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const paths: string[] = [];
    for (const name of await caches.keys()) {
      for (const request of await (await caches.open(name)).keys()) paths.push(new URL(request.url).pathname);
    }
    return paths;
  });
}

test("M7e-E1: the manifest and its icons are valid and load without a session", async ({ request, page }) => {
  const response = await request.get("/manifest.webmanifest", { maxRedirects: 0 });
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toMatch(/application\/manifest\+json/);
  const manifest = (await response.json()) as { start_url: string; display: string; icons: { src: string; sizes: string; purpose: string }[] };
  expect(manifest).toMatchObject({ start_url: "/", display: "standalone" });
  expect(manifest.icons.map((i) => i.purpose)).toEqual(["any", "any", "maskable"]);
  for (const icon of manifest.icons) {
    const file = await request.get(icon.src, { maxRedirects: 0 });
    expect(file.status(), icon.src).toBe(200);
    expect(file.headers()["content-type"]).toBe("image/png");
  }
  for (const path of ["/sw.js", "/sw-register.js", "/offline.html"]) {
    expect((await request.get(path, { maxRedirects: 0 })).status(), path).toBe(200);
  }

  // The staff and portal pages link the manifest and carry the theme colour (design §7 Q2, B);
  // the landing page and search leave them out to stay within 200 KB.
  await page.goto("/portal/sign-in");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
  await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#147d72");
  for (const path of ["/", "/find"]) {
    await page.goto(path);
    await expect(page.locator('link[rel="manifest"]')).toHaveCount(0);
    await expect(page.locator('script[src="/sw-register.js"]')).toHaveCount(0);
  }
});

test("M7e-E1: the service worker takes over, never caches the API or a page, and shows the offline page", async ({ page, context }) => {
  test.setTimeout(60_000);
  // The staff and portal pages register the worker (design §7 Q2); its scope covers the whole site.
  await page.goto("/portal/sign-in");
  // `ready` resolves once a worker is active; it may still be finishing its activation.
  await expect
    .poll(() => page.evaluate(async () => (await navigator.serviceWorker.ready).active?.state))
    .toBe("activated");
  await page.goto("/find");
  // A page that does not register the worker (search) is still in its scope and under its control.
  expect(await page.evaluate(() => navigator.serviceWorker.controller !== null)).toBe(true);

  // An API call made by the page goes to the network, not the service worker.
  const api = page.waitForResponse((r) => r.url().includes("/api/v1/public/search/doctors"));
  await page.evaluate(() => fetch("/api/v1/public/search/doctors").then((r) => r.status));
  expect((await api).fromServiceWorker()).toBe(false);

  // Visit a few pages, then read the cache: build assets, logo, icons and the offline page only.
  for (const path of ["/", "/c/sample-clinic", "/portal/sign-in"]) await page.goto(path);
  const cached = await cachedPaths(page);
  expect(cached).toContain("/offline.html");
  expect(cached.filter((p) => !/^\/(_next\/static\/|brand\/|icons\/|offline\.html$)/.test(p))).toEqual([]);

  // Offline: a page that cannot load shows the offline page, at 360 px, accessible.
  await page.setViewportSize({ width: 360, height: 740 });
  await context.setOffline(true);
  await page.goto("/portal/appointments");
  await expect(page.getByRole("heading", { level: 1, name: "You are offline" })).toBeVisible();
  await expect(page.getByText("Nothing was sent or changed.")).toBeVisible();
  await expect(page.locator('[lang="hi"]')).toContainText("आप ऑफ़लाइन हैं");
  await noHorizontalScroll(page);
  await expectAccessible(page);

  // Back online, Try again loads the real page.
  await context.setOffline(false);
  await page.getByRole("link", { name: "Try again" }).click();
  await expect(page).toHaveURL(/\/$|\/(find|portal)/);
  await expect(page.getByRole("heading", { level: 1, name: "You are offline" })).toHaveCount(0);
});
