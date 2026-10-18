/**
 * M4-P5 (FR-RX-07, 08; spec AC2, AC3, R11, R19, NFR-02): the patient opens their prescription
 * link on a 360-px phone. Setup through the API as the seeded staff: a visit in a session
 * running now, the PRD §8.6 sample issued, the link from the front desk. The synthetic patient's
 * phone ends in 0101 (queue-support.ts).
 */

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { DESK, DOCTOR, newPatient, sessionRunningNow, signInApi } from "./queue-support";

const SAMPLE = {
  medicine_name: "Syrup X",
  dose: "5 ml",
  frequency: "1-0-1",
  timing: "AFTER_FOOD",
  duration_days: 5,
  preparation: [{ code: "SHAKE_WELL" }, { code: "DILUTE_IN_WATER", text: "10 ml" }],
  storage: [{ code: "DISCARD_AFTER_DAYS", days: 7 }],
};

async function issuedLink(request: APIRequestContext): Promise<string> {
  const { sessionId } = await sessionRunningNow(request);
  const patient = await newPatient(request, "Isha");
  let csrf = await signInApi(request, DESK);
  const booked = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": csrf },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(booked.status(), await booked.text()).toBe(201);
  const appointment = ((await booked.json()) as { id: string }).id;
  for (const [from, to] of [["BOOKED", "ARRIVED"], ["ARRIVED", "IN_CONSULTATION"]]) {
    const moved = await request.post(`/api/v1/appointments/${appointment}/transitions`, {
      headers: { "X-CSRF-Token": csrf },
      data: { from, to },
    });
    expect(moved.status(), await moved.text()).toBe(200);
  }
  const me = (await (await request.get("/api/v1/me")).json()) as { memberships: { clinic_id: string }[] };
  const clinicId = me.memberships[0]?.clinic_id ?? "";
  csrf = await signInApi(request, DOCTOR);
  // The seeded doctor also works at Sample Clinic Two, so every call names the clinic.
  const headers = { "X-CSRF-Token": csrf, "X-Clinic-ID": clinicId };
  const started = await request.post("/api/v1/visits", { headers, data: { appointment_id: appointment } });
  expect(started.status(), await started.text()).toBe(201);
  const visit = (await started.json()) as { id: string };
  const created = await request.post(`/api/v1/visits/${visit.id}/prescriptions`, { headers });
  expect(created.status(), await created.text()).toBe(201);
  const rx = (await created.json()) as { id: string };
  const saved = await request.put(`/api/v1/prescriptions/${rx.id}`, {
    headers,
    data: { revision: 1, items: [SAMPLE], advice: { return_if: ["breathing is difficult"] } },
  });
  expect(saved.status(), await saved.text()).toBe(200);
  const issued = await request.post(`/api/v1/prescriptions/${rx.id}/issue`, { headers, data: { revision: 2 } });
  expect(issued.status(), await issued.text()).toBe(200);
  await signInApi(request, DESK);
  const link = (await (await request.get(`/api/v1/prescriptions/${rx.id}/link`)).json()) as { url: string };
  return new URL(link.url).pathname; // the stack's PUBLIC_BASE_URL may differ from the e2e host
}

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
  const card = page.getByRole("listitem").filter({ hasText: "Syrup X" });
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
  await expect(first.getByRole("listitem").filter({ hasText: "Syrup X" })).toBeVisible();
  const loaded = await Promise.all(transfers);
  const total = loaded.reduce((sum, t) => sum + t.bytes, 0);
  console.log(`NFR-02 page weight: ${total} bytes in ${loaded.length} responses`, loaded.map((t) => `${t.bytes} ${new URL(t.url).pathname}`).join("; "));
  await fresh.close();
  expect(total, "NFR-02: under 200 KB for the page and its assets").toBeLessThan(200 * 1024);

  await page.getByRole("link", { name: "हिन्दी में देखें" }).click();
  await expect(page.getByRole("heading", { name: "दवाइयाँ" })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Syrup X" })).toContainText("कैसे दें");
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
