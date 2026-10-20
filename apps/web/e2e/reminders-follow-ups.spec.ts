/**
 * M5-P6 (FR-REM-02, 05, 07; spec R16-R18; decision 7A): a prescription issued with a follow-up
 * date shows its reminder on the consultation and on the profile, with the message history; the
 * front desk books an overdue follow-up from the pending list; ops read the month's messaging
 * costs. Uses `make seed` data (including its one overdue follow-up), a session running now and a
 * fresh synthetic patient, so it passes at any hour and on a reused database.
 */

import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

import { DESK, DOCTOR, PASSWORD, newPatient, sessionRunningNow, signInApi } from "./queue-support";

const OPS = "ops@mediease.example";
const ZONE = "Asia/Kolkata";

async function as(browser: Browser, email: string, landing: RegExp = /\/(queue|select-clinic)$/): Promise<Page> {
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 768 } })).newPage();
  await page.goto("/sign-in");
  await page.getByLabel("Email or phone number").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(landing);
  // The seeded doctor works in both sample clinics, so they choose this one first.
  if (page.url().endsWith("/select-clinic")) {
    await page.getByRole("button", { name: /^Sample Clinic\b(?! Two)/ }).click();
    await expect(page).toHaveURL(/\/queue$/);
  }
  return page;
}

function inDays(days: number): string {
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    new Date(Date.now() + days * 86_400_000),
  );
  return day;
}

async function ok(resp: Awaited<ReturnType<APIRequestContext["post"]>>, status = 200) {
  expect(resp.status(), await resp.text()).toBe(status);
  return (await resp.json()) as Record<string, unknown>;
}

/** A consenting patient seen today, with a prescription issued with a follow-up in 5 days. */
async function issuedWithFollowUp(request: APIRequestContext): Promise<{ patientId: string; name: string; visitId: string }> {
  const { sessionId } = await sessionRunningNow(request);
  const patient = await newPatient(request, "Ira");
  const desk = await signInApi(request, DESK);
  const headers = { "X-CSRF-Token": desk };
  await ok(await request.put(`/api/v1/patients/${patient.id}/consent`, { headers, data: { whatsapp: true, sms: false } }));
  const booked = await ok(await request.post("/api/v1/appointments", { headers, data: { session_id: sessionId, patient_id: patient.id } }), 201);
  for (const [from, to] of [["BOOKED", "ARRIVED"], ["ARRIVED", "IN_CONSULTATION"]]) {
    await ok(await request.post(`/api/v1/appointments/${String(booked.id)}/transitions`, { headers, data: { from, to } }));
  }

  const doctor = await signInApi(request, DOCTOR);
  const me = (await (await request.get("/api/v1/me")).json()) as { memberships: { clinic_id: string; clinic_name: string }[] };
  const clinicId = me.memberships.find((m) => m.clinic_name === "Sample Clinic")?.clinic_id ?? "";
  const as = { "X-CSRF-Token": doctor, "X-Clinic-ID": clinicId };
  const visit = await ok(await request.post("/api/v1/visits", { headers: as, data: { appointment_id: booked.id } }), 201);
  const draft = await ok(await request.post(`/api/v1/visits/${String(visit.id)}/prescriptions`, { headers: as }), 201);
  await ok(
    await request.put(`/api/v1/prescriptions/${String(draft.id)}`, {
      headers: as,
      data: {
        revision: draft.revision,
        items: [{ medicine_name: "Syrup X", dose: "5 ml", frequency: "1-0-1", timing: "AFTER_FOOD", duration_days: 5 }],
        advice: {},
        follow_up_date: inDays(5),
      },
    }),
  );
  await ok(await request.post(`/api/v1/prescriptions/${String(draft.id)}/issue`, { headers: as, data: { revision: 2 } }));
  return { patientId: patient.id, name: patient.name, visitId: String(visit.id) };
}

test("R16: the issued follow-up's reminder shows on the consultation and the profile, with the message history", async ({ browser, request }) => {
  test.setTimeout(90_000);
  const issued = await issuedWithFollowUp(request);

  const doctor = await as(browser, DOCTOR);
  await doctor.goto(`/visits/${issued.visitId}`);
  await expect(doctor.getByRole("heading", { name: "Prescription issued" })).toBeVisible();
  await expect(doctor.getByText(/^Follow-up reminder · .+, 09:00 · (Scheduled|Sent|Delivered|Read)$/)).toBeVisible();

  const desk = await as(browser, DESK);
  await desk.goto(`/patients/${issued.patientId}`);
  const reminders = desk.getByRole("region", { name: "Reminders" });
  await expect(reminders.getByText(/^Follow-up reminder · /)).toBeVisible();
  await expect(reminders).toContainText("From a prescription");
  // The prescription link goes out through the worker: reload until it is listed.
  const history = desk.getByRole("region", { name: "Message history" });
  await expect(async () => {
    await desk.reload();
    await expect(history.getByRole("row", { name: /Prescription link/ })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  await expect(history).not.toContainText("MSG_");
});

test("FR-REM-07: the front desk books an overdue follow-up from the pending list", async ({ browser, request }) => {
  test.setTimeout(60_000);
  await sessionRunningNow(request);
  const token = await signInApi(request, DESK);
  const pending = (await (await request.get("/api/v1/follow-ups/pending")).json()) as {
    items: { patient_id: string; patient_name: string }[];
  };
  const seeded = pending.items.find((i) => i.patient_name === "Deepa Nair");
  expect(seeded, "make seed adds one overdue follow-up").toBeDefined();
  // A rerun on the same day: free the patient from today's earlier booking first.
  const theirs = (await (await request.get(`/api/v1/patients/${seeded?.patient_id ?? ""}/appointments`)).json()) as {
    items: { id: string; status: string; on_date: string }[];
  };
  for (const a of theirs.items.filter((i) => i.status === "BOOKED" && i.on_date === inDays(0))) {
    await ok(await request.post(`/api/v1/appointments/${a.id}/cancel`, { headers: { "X-CSRF-Token": token }, data: { reason: "PATIENT_REQUEST" } }));
  }

  const desk = await as(browser, DESK);
  await desk.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Follow-ups" }).click();
  await expect(desk).toHaveURL(/\/follow-ups$/);
  await expect(desk.getByRole("heading", { level: 1, name: "Pending follow-ups" })).toBeVisible();
  const row = desk.getByRole("row").filter({ hasText: "Deepa Nair" });
  await row.getByRole("button", { name: "Book follow-up for Deepa Nair" }).click();
  const drawer = desk.getByRole("dialog", { name: "Book appointment" });
  await expect(drawer).toContainText("Deepa Nair");
  await expect(drawer.getByRole("radio", { checked: true })).toHaveCount(1);
  await drawer.getByRole("button", { name: "Confirm booking" }).click();

  await expect(desk.getByRole("status").filter({ hasText: "Deepa Nair booked" })).toBeVisible();
  await expect(row).toContainText("Booked");
});

test("R18: ops read this month's messaging costs per clinic", async ({ browser }) => {
  const ops = await as(browser, OPS, /\/ops$/);
  await ops.getByRole("navigation", { name: "Ops" }).getByRole("link", { name: "Messaging costs" }).click();
  await expect(ops).toHaveURL(/\/ops\/messaging-costs$/);
  await expect(ops.getByRole("heading", { level: 1, name: "Messaging costs" })).toBeVisible();
  await expect(ops.getByLabel("Month")).toHaveValue(inDays(0).slice(0, 7));
  await expect(ops.getByText(/^Total: ₹|^No messages were sent in this month\.$/)).toBeVisible();
  await expect(ops.getByText(/excluding GST/)).toBeVisible();
});
