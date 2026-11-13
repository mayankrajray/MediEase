import { createECDH, randomBytes } from "node:crypto";

import { expect, test, type Page } from "@playwright/test";

import { expectAccessible, noHorizontalScroll, signInWithGoogle } from "./portal-support";
import { DESK, signInAs } from "./queue-support";

/**
 * M7e-E5 (spec web-push R50-R54; design §7 Q4 A): turning pop-up alerts on and off for this
 * device, on the real stack and API. A container cannot reach the browsers' push services, so the
 * browser's push manager and permission prompt are stubbed, and the push config answers with a
 * synthetic public key (CI runs without VAPID keys). The device the API stores is real. Real
 * delivery is checked on the developer's phone through a tunnel (RUNBOOK §36).
 */

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
test.use({ channel: "chromium", launchOptions: { args: [`--unsafely-treat-insecure-origin-as-secure=${new URL(BASE).origin}`] } });

const b64 = (bytes: Buffer) => bytes.toString("base64url");
/** A real uncompressed P-256 public key (the API refuses a point that is not on the curve). */
const point = () => b64(createECDH("prime256v1").generateKeys());
const PUBLIC_KEY = point();

/** A fake browser subscription at FCM, and a permission prompt that says yes. */
async function stubPush(page: Page): Promise<string> {
  const endpoint = `https://fcm.googleapis.com/fcm/send/e2e-${randomBytes(8).toString("hex")}:APA91b-e2e`;
  const keys = { p256dh: point(), auth: b64(randomBytes(16)) };
  await page.addInitScript(
    ({ endpoint, keys }) => {
      let permission: NotificationPermission = "default";
      let current: PushSubscription | null = null;
      Object.defineProperty(Notification, "permission", { get: () => permission, configurable: true });
      Notification.requestPermission = async () => (permission = "granted");
      PushManager.prototype.getSubscription = async () => current;
      PushManager.prototype.subscribe = async () => {
        current = {
          endpoint,
          options: { applicationServerKey: null, userVisibleOnly: true },
          toJSON: () => ({ endpoint, expirationTime: null, keys }),
          unsubscribe: async () => {
            current = null;
            return true;
          },
        } as unknown as PushSubscription;
        return current;
      };
    },
    { endpoint, keys },
  );
  await page.route("**/api/v1/push/config", (route) => route.fulfill({ json: { enabled: true, public_key: PUBLIC_KEY } }));
  return endpoint;
}

async function devices(page: Page, path: string): Promise<{ active: boolean }[]> {
  const response = await page.request.get(path);
  expect(response.status()).toBe(200);
  return ((await response.json()) as { items: { active: boolean }[] }).items;
}

test("M7e-E5: a patient turns pop-up alerts on and off for this phone, and per kind", async ({ browser }) => {
  test.setTimeout(90_000);
  const context = await browser.newContext({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  await stubPush(page);
  await signInWithGoogle(page, `push.e2e.${Date.now()}@example.test`);
  await page.goto("/portal/account");
  await expect.poll(() => page.evaluate(async () => (await navigator.serviceWorker.ready).active?.state)).toBe("activated");

  const card = page.locator("section", { has: page.getByRole("heading", { name: "Pop-up alerts on this device" }) });
  await expect(card.getByText("Off for this device.")).toBeVisible();
  await card.getByRole("button", { name: "Turn on" }).click();
  await expect(card.getByText("On for this device.")).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Pop-up alerts are on for this device." })).toBeVisible();
  expect(await devices(page, "/api/v1/portal/push-subscriptions")).toEqual([expect.objectContaining({ active: true })]);
  await noHorizontalScroll(page);
  await expectAccessible(page);

  // Which kinds alert: a switch of its own beside "In the app".
  const due = page.getByRole("group", { name: "Medicine time" });
  // The switch shows the saved state, so it changes once the server has answered.
  await due.getByRole("checkbox", { name: "Pop-up alert" }).click();
  await expect(due.getByRole("checkbox", { name: "Pop-up alert" })).not.toBeChecked();
  await expect(page.getByRole("status").filter({ hasText: "Notification settings saved." })).toBeVisible();
  await expect(due.getByRole("checkbox", { name: "In the app" })).toBeChecked();

  await card.getByRole("button", { name: "Turn off" }).click();
  await expect(card.getByText("Off for this device.")).toBeVisible();
  expect(await devices(page, "/api/v1/portal/push-subscriptions")).toEqual([]);
  await context.close();
});

test("M7e-E5: a staff member turns pop-up alerts on for this computer", async ({ page }) => {
  test.setTimeout(90_000);
  await stubPush(page);
  await signInAs(page, DESK);
  await page.goto("/settings/notifications");
  await expect(page.getByRole("group", { name: "Pop-up alerts" })).toBeVisible();
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByText("On for this device.", { exact: true })).toBeVisible();
  expect(await devices(page, "/api/v1/me/push-subscriptions")).toEqual(expect.arrayContaining([expect.objectContaining({ active: true })]));
  await expectAccessible(page);
  await page.getByRole("button", { name: "Turn off" }).click();
  await expect(page.getByText("Off for this device.", { exact: true })).toBeVisible();
});
