import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

import { askFor, clinicClock, lonelySession, type Lonely } from "./booking-support";
import { expectAccessible, firstLoadBytes, noHorizontalScroll } from "./portal-support";
import { DESK, newPatient, openQueue, sessionRunningNow, signInApi, signInAs } from "./queue-support";

/**
 * M6b-P6 (spec patient-portal R55-R72, AC23, AC24, AC27): the patient is told in the app when the
 * desk answers, and follows their place in the queue on the live token page, at 360 px.
 */

test.setTimeout(240_000);

async function phone(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });
  return { context, page: await context.newPage() };
}

function rowFor(page: Page, number: string) {
  return page.getByRole("row").filter({ has: page.getByRole("link", { name: `+91${number}` }) });
}

async function newRecord(drawer: ReturnType<Page["getByRole"]>) {
  await drawer.getByRole("radio", { name: "Create new record" }).check();
  await drawer.getByLabel("Sex (required)").selectOption("FEMALE");
  await drawer.getByLabel("Age in years (required)").fill("30");
}

test("AC23: the bell tells the patient when the desk accepts and when it offers another time", async ({ page, browser, request }) => {
  const sessions: Lonely[] = [];
  for (let i = 0; i < 3; i += 1) sessions.push(await lonelySession(request));
  const [toAccept, toPropose, offered] = sessions as [Lonely, Lonely, Lonely];
  const p1 = await phone(browser);
  const p2 = await phone(browser);
  const phone1 = await askFor(p1.page, toAccept, "bell.accept");
  const phone2 = await askFor(p2.page, toPropose, "bell.propose");
  // Nothing to tell yet.
  await expect(p1.page.getByRole("link", { name: "Notifications", exact: true })).toBeVisible();

  await signInAs(page, DESK);
  await page.goto("/booking-requests");
  await rowFor(page, phone1).getByRole("button", { name: /^Accept / }).click();
  const accept = page.getByRole("dialog", { name: "Accept request" });
  await newRecord(accept);
  await accept.getByRole("button", { name: "Accept and book" }).click();
  await expect(page.getByRole("status").filter({ hasText: "accepted and booked" })).toBeVisible();

  await rowFor(page, phone2).getByRole("button", { name: /^Propose another time/ }).click();
  const propose = page.getByRole("dialog", { name: "Propose another time" });
  await propose.getByLabel("Date").fill(offered.onDate);
  await propose.getByRole("radio", { name: new RegExp(`^${clinicClock(offered.startsAt)}`) }).check();
  await newRecord(propose);
  await propose.getByRole("button", { name: "Offer this time" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Another time offered" })).toBeVisible();

  // The accepted patient: one unread, its title names the clinic, opening it clears the bell.
  await p1.page.goto("/portal");
  const bell = p1.page.getByRole("link", { name: "Notifications, 1 unread" });
  await expect(bell).toBeVisible();
  await bell.click();
  await expect(p1.page).toHaveURL(/\/portal\/notifications$/);
  const list = p1.page.getByRole("list", { name: "Notifications" });
  await expect(list.getByRole("link")).toHaveCount(1);
  await expect(list).toContainText("Booked: ");
  await expect(list).toContainText("Sample Clinic");
  await expectAccessible(p1.page);
  await noHorizontalScroll(p1.page);
  await list.getByRole("link").first().click();
  await expect(p1.page).toHaveURL(/\/portal\/appointments$/);
  await expect(p1.page.getByRole("link", { name: "Notifications", exact: true })).toBeVisible();

  // The other patient is told the clinic suggests another time, and answers from the link.
  await p2.page.goto("/portal/notifications");
  const theirs = p2.page.getByRole("list", { name: "Notifications" });
  await expect(theirs).toContainText("suggests another time");
  await p2.page.getByRole("button", { name: "Mark all as read" }).click();
  await expect(p2.page.getByRole("status").filter({ hasText: "All notifications marked as read." })).toBeVisible();
  await expect(p2.page.getByRole("link", { name: "Notifications", exact: true })).toBeVisible();
  await theirs.getByRole("link").first().click();
  await expect(p2.page.getByRole("region", { name: "Requested" })).toContainText("Suggested another time");

  for (const p of [p1, p2]) await p.context.close();
});

/** "3 people ahead of you" -> 3; "Nobody is ahead of you." -> 0. */
async function aheadOf(page: Page): Promise<number> {
  const text = (await page.getByText(/ahead of you/).first().textContent()) ?? "";
  const n = /^(\d+)/.exec(text);
  return n === null ? 0 : Number(n[1]);
}

test("AC27: the live link follows the queue as the desk moves it", async ({ page, browser, request }) => {
  const { sessionId } = await sessionRunningNow(request);
  const before = await newPatient(request, "Kavi");
  const mine = await newPatient(request, "Meera");
  const csrf = await signInApi(request, DESK);
  const ids: string[] = [];
  for (const p of [before, mine]) {
    const booked = await request.post("/api/v1/appointments", {
      headers: { "X-CSRF-Token": csrf },
      data: { session_id: sessionId, patient_id: p.id },
    });
    expect(booked.status(), await booked.text()).toBe(201);
    ids.push(((await booked.json()) as { id: string }).id);
  }
  const [beforeId, mineId] = ids as [string, string];

  // The desk copies the link from the queue row's menu.
  await signInAs(page, DESK);
  await openQueue(page);
  await page.getByRole("button", { name: `More actions for ${mine.name}` }).click();
  await page.getByRole("menuitem", { name: "Copy live link" }).click();
  await expect(page.getByRole("status").filter({ hasText: `Live link for ${mine.name}` })).toBeVisible();
  const link = (await (await request.get(`/api/v1/appointments/${mineId}/live-link`)).json()) as { url: string };

  // The patient opens it on a phone, signed out: no names, their token, who is ahead.
  const p = await phone(browser);
  await p.page.goto(new URL(link.url).pathname);
  await expect(p.page.getByRole("heading", { level: 2, name: /^Your token: \d+$/ })).toBeVisible();
  await expect(p.page.getByText("Please wait; you will be called.")).toBeVisible();
  await expect(p.page.locator("body")).not.toContainText(mine.name);
  await expect(p.page.locator("body")).not.toContainText(before.name);
  await expectAccessible(p.page);
  await noHorizontalScroll(p.page);
  // NFR-02: a patient-facing page under 200 KB on a first visit.
  const bytes = await firstLoadBytes(browser, p.page, new URL(link.url).pathname, async (f) => {
    await expect(f.getByRole("heading", { level: 2, name: /^Your token: / })).toBeVisible();
  });
  expect(bytes).toBeLessThan(200 * 1024);
  const ahead = await aheadOf(p.page);
  expect(ahead).toBeGreaterThanOrEqual(1);

  // The patient before them goes in: one fewer ahead, without a reload (polls every 20 s).
  for (const [from, to] of [["BOOKED", "ARRIVED"], ["ARRIVED", "IN_CONSULTATION"]]) {
    const moved = await request.post(`/api/v1/appointments/${beforeId}/transitions`, { headers: { "X-CSRF-Token": csrf }, data: { from, to } });
    expect(moved.status(), await moved.text()).toBe(200);
  }
  const expected = ahead - 1 === 0 ? "Nobody is ahead of you." : ahead - 1 === 1 ? "1 person ahead of you" : `${ahead - 1} people ahead of you`;
  await expect(p.page.getByText(expected)).toBeVisible({ timeout: 30_000 });

  // Their own turn.
  for (const [from, to] of [["BOOKED", "ARRIVED"], ["ARRIVED", "IN_CONSULTATION"]]) {
    const moved = await request.post(`/api/v1/appointments/${mineId}/transitions`, { headers: { "X-CSRF-Token": csrf }, data: { from, to } });
    expect(moved.status(), await moved.text()).toBe(200);
  }
  await expect(p.page.getByText("It is your turn. Please go in.")).toBeVisible({ timeout: 30_000 });

  // Hindi on request; a forged link says it is not valid.
  await p.page.goto(`${new URL(link.url).pathname}?lang=hi`);
  await expect(p.page.getByText("आपकी बारी है। कृपया अंदर जाएँ।")).toBeVisible();
  await p.page.goto(`${new URL(link.url).pathname.slice(0, -4)}AAAA`);
  await expect(p.page.getByRole("alert").filter({ hasText: "This link is not valid." })).toHaveText(
    "This link is not valid. Please ask the clinic for a new one.",
  );
  await p.context.close();
});
