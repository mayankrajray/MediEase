import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";

import { askFor, clinicClock, DOCTOR_NAME, lonelySession, type Lonely } from "./booking-support";
import { expectAccessible } from "./portal-support";
import { DESK, signInAs } from "./queue-support";

/**
 * M6b-P5 (FR-BKG-04, 05, FR-PRT-06 a; spec booking-requests AC9, AC13, AC14): the real front desk
 * -> patient flow. Three patients ask for times on their phones; the desk accepts one with a new
 * record (the patient then sees the appointment under the clinic), offers another time to the
 * second (who accepts it with one tap) and declines the third (who sees why and the call button).
 */

test.setTimeout(240_000);

async function patientPage(browser: Browser): Promise<{ context: BrowserContext; page: Page }> {
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

async function openInbox(page: Page) {
  await page.goto("/booking-requests");
  await expect(page.getByRole("heading", { name: "Booking requests" })).toBeVisible();
}

test("the desk accepts, proposes and declines; each patient sees the answer", async ({ page, browser, request }) => {
  const sessions: Lonely[] = [];
  for (let i = 0; i < 4; i += 1) sessions.push(await lonelySession(request));
  const [toAccept, toPropose, proposedTime, toDecline] = sessions as [Lonely, Lonely, Lonely, Lonely];

  const p1 = await patientPage(browser);
  const p2 = await patientPage(browser);
  const p3 = await patientPage(browser);
  const phone1 = await askFor(p1.page, toAccept, "accept.me");
  const phone2 = await askFor(p2.page, toPropose, "propose.me");
  const phone3 = await askFor(p3.page, toDecline, "decline.me");

  await signInAs(page, DESK);
  await openInbox(page);
  await expectAccessible(page);

  // Accept with a new record: booked, and the patient's app is linked to it (AC9).
  await rowFor(page, phone1).getByRole("button", { name: /^Accept / }).click();
  const accept = page.getByRole("dialog", { name: "Accept request" });
  await newRecord(accept);
  await expectAccessible(page);
  await accept.getByRole("button", { name: "Accept and book" }).click();
  await expect(page.getByRole("status").filter({ hasText: "accepted and booked" })).toBeVisible();

  await p1.page.goto("/portal/appointments");
  await expect(p1.page.getByRole("region", { name: "Sample Clinic" })).toContainText(DOCTOR_NAME);
  await expect(p1.page.getByRole("region", { name: "Requested" })).toHaveCount(0);

  // Propose another time; the patient accepts it with one tap (AC14).
  await rowFor(page, phone2).getByRole("button", { name: /^Propose another time/ }).click();
  const propose = page.getByRole("dialog", { name: "Propose another time" });
  await propose.getByLabel("Date").fill(proposedTime.onDate);
  await propose.getByRole("radio", { name: new RegExp(`^${clinicClock(proposedTime.startsAt)}`) }).check();
  await newRecord(propose);
  await propose.getByRole("button", { name: "Offer this time" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Another time offered" })).toBeVisible();
  await expect(rowFor(page, phone2)).toContainText("Waiting for the patient");

  await p2.page.goto("/portal/appointments");
  const offered = p2.page.getByRole("region", { name: "Requested" });
  await expect(offered).toContainText("Suggested another time");
  await expectAccessible(p2.page);
  await offered.getByRole("button", { name: "Accept this time" }).click();
  await expect(p2.page.getByRole("region", { name: "Sample Clinic" })).toContainText(DOCTOR_NAME);

  // Decline with a reason the patient reads, and a call button (AC13).
  await openInbox(page);
  await rowFor(page, phone3).getByRole("button", { name: /^Decline / }).click();
  const decline = page.getByRole("dialog", { name: /^Decline / });
  await decline.getByRole("radio", { name: "Please call the clinic" }).check();
  await decline.getByLabel("Note for the clinic (optional)").fill("synthetic staff note");
  await decline.getByRole("button", { name: "Decline request" }).click();
  await expect(page.getByRole("status").filter({ hasText: "declined" })).toBeVisible();

  await p3.page.goto("/portal/appointments");
  const declined = p3.page.getByRole("region", { name: "Requested" });
  await expect(declined).toContainText("Please call the clinic.");
  await expect(declined.getByRole("link", { name: "Call the clinic" })).toHaveAttribute("href", /^tel:/);
  await expect(declined).not.toContainText("synthetic staff note");

  // The answered list shows all three outcomes.
  await page.getByRole("button", { name: "Answered" }).click();
  const answered = page.getByRole("table");
  await expect(rowFor(page, phone1)).toContainText("Accepted");
  await expect(rowFor(page, phone2)).toContainText("Accepted");
  await expect(rowFor(page, phone3)).toContainText("Declined");
  await expect(answered).toBeVisible();

  for (const p of [p1, p2, p3]) await p.context.close();
});
