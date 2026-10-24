/**
 * Shared e2e set-up for patient pages (M4-P5, M6b-P2): an issued PRD §8.6 sample and its patient
 * link, made through the API as the seeded staff; page weight and accessibility checks.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, type APIRequestContext, type Browser, type Page } from "@playwright/test";

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

/** The issued sample's link path (`/p/<token>`); the synthetic patient's phone ends in 0101. */
export async function issuedLink(request: APIRequestContext): Promise<string> {
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

/** NFR-02: bytes on the wire for a first visit in a fresh browser with this page's session. */
export async function firstLoadBytes(browser: Browser, page: Page, path: string, ready: (p: Page) => Promise<void>): Promise<number> {
  const fresh = await browser.newContext({ storageState: await page.context().storageState(), viewport: { width: 360, height: 640 } });
  const first = await fresh.newPage();
  const transfers: Promise<number>[] = [];
  first.on("requestfinished", (req) => {
    transfers.push(
      Promise.all([req.sizes(), req.response()]).then(async ([s, resp]) => {
        const encoded = Number(resp?.headers()["content-length"] ?? Number.NaN);
        const body = s.responseBodySize > 0 ? s.responseBodySize : Number.isFinite(encoded) ? encoded : ((await resp?.body())?.length ?? 0);
        return body + s.responseHeadersSize;
      }),
    );
  });
  await first.goto(path, { waitUntil: "networkidle" });
  await ready(first);
  const total = (await Promise.all(transfers)).reduce((sum, n) => sum + n, 0);
  await fresh.close();
  return total;
}

/** NFR-10: no serious or critical WCAG 2.1 A/AA violation on the page as it is now. */
export async function expectAccessible(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(serious, `axe on ${page.url()}`).toEqual([]);
}

export async function noHorizontalScroll(page: Page): Promise<void> {
  const widths = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(widths[0]).toBeLessThanOrEqual(widths[1] ?? 0);
}