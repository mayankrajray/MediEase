import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { DESK, DOCTOR, OWNER, newPatient, sessionRunningNow, signInApi, signInAs } from "./queue-support";

/**
 * M6a-P6 (FR-UX-01..06): each role's home, navigation and first three actions differ at
 * 1366×768, and a practising owner switches to the Doctor view and sees only their own sessions
 * and patients. Uses `make seed` (RUNBOOK §1), including `sample-family-clinic`.
 */

const FAMILY_OWNER = "owner@sample-family-clinic.example";
const FAMILY_DOCTOR = "doctor@sample-family-clinic.example";
const FAMILY_DESK = "desk@sample-family-clinic.example";
const OWNER_DOCTOR_NAME = "Dr. Family Owner";
const COLLEAGUE_NAME = "Dr. Family Colleague";

test.use({ viewport: { width: 1366, height: 768 } });

async function home(page: Page): Promise<{ nav: string[]; actions: string[] }> {
  await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
  const quick = page.getByRole("navigation", { name: "Quick actions" });
  await expect(quick.getByRole("listitem")).toHaveCount(3);
  return {
    // M6b-P5: the open-request count rides on its link's name and depends on the data; drop it.
    nav: (await page.getByRole("navigation", { name: "Main" }).getByRole("link").allTextContents()).map((t) => t.replace(/, \d+ waiting$/, "")),
    actions: await quick.getByRole("listitem").allTextContents(),
  };
}

test("FR-UX-05: the owner, the doctor and the front desk each get their own home, menu and first actions", async ({
  browser,
}) => {
  const seen: Record<string, { nav: string[]; actions: string[] }> = {};
  for (const [who, email] of [
    ["owner", OWNER],
    ["doctor", DOCTOR],
    ["desk", DESK],
  ] as const) {
    const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    const page = await context.newPage();
    await signInAs(page, email);
    seen[who] = await home(page);
    await context.close();
  }

  expect(seen["owner"]).toEqual({
    nav: ["Today", "Queue", "Booking requests", "Patients", "Follow-ups", "Bills", "Dues", "Collection", "Team", "Schedule", "Audit log", "Directory", "Fees", "Plan", "Notifications"],
    actions: ["Invite someone", "Schedule settings", "See the queue"],
  });
  expect(seen["doctor"]).toEqual({
    nav: ["Today", "My queue", "My patients", "My follow-ups", "My schedule", "My bills", "Notifications"],
    actions: ["Open my queue", "My patients", "My follow-ups"],
  });
  expect(seen["desk"]).toEqual({
    nav: ["Today", "Queue", "Booking requests", "Patients", "Follow-ups", "Bills", "Dues", "Collection", "Notifications"],
    actions: ["Register a patient", "Book an appointment", "Add a walk-in"],
  });
});

/** A patient booked now with `doctorName` and seen by `doctorEmail` (their visit is started). */
async function seenBy(request: APIRequestContext, doctorName: string, doctorEmail: string, label: string): Promise<string> {
  const { sessionId } = await sessionRunningNow(request, { owner: FAMILY_OWNER, doctorName });
  const patient = await newPatient(request, label, FAMILY_DESK);
  const desk = await signInApi(request, FAMILY_DESK);
  const booked = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": desk },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(booked.status(), await booked.text()).toBe(201);
  const appointment = ((await booked.json()) as { id: string }).id;
  for (const [from, to] of [
    ["BOOKED", "ARRIVED"],
    ["ARRIVED", "IN_CONSULTATION"],
  ]) {
    const moved = await request.post(`/api/v1/appointments/${appointment}/transitions`, {
      headers: { "X-CSRF-Token": desk },
      data: { from, to },
    });
    expect(moved.status(), await moved.text()).toBe(200);
  }
  const doctor = await signInApi(request, doctorEmail);
  const visit = await request.post("/api/v1/visits", {
    headers: { "X-CSRF-Token": doctor },
    data: { appointment_id: appointment },
  });
  expect(visit.status(), await visit.text()).toBe(201);
  return patient.name;
}

test("FR-UX-06: a practising owner switches to Doctor and sees only their own sessions and patients", async ({
  page,
  request,
}) => {
  const mine = await seenBy(request, OWNER_DOCTOR_NAME, FAMILY_OWNER, "Owner");
  const colleagues = await seenBy(request, COLLEAGUE_NAME, FAMILY_DOCTOR, "Colleague");

  await signInAs(page, FAMILY_OWNER);
  const owner = await home(page);
  expect(owner.nav).toContain("Team");
  const view = page.getByRole("group", { name: "View" });
  await expect(view.getByRole("radio", { name: "Owner" })).toBeChecked();

  await view.getByText("Doctor", { exact: true }).click();
  await expect(view.getByRole("radio", { name: "Doctor" })).toBeChecked();
  const doctor = await home(page);
  expect(doctor.nav).toEqual(["Today", "My queue", "My patients", "My follow-ups", "My schedule", "My bills", "Notifications"]);
  const sessions = page.getByRole("region", { name: "Your sessions" });
  await expect(sessions).toContainText(OWNER_DOCTOR_NAME);
  await expect(sessions).not.toContainText(COLLEAGUE_NAME);

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "My patients" }).click();
  await expect(page).toHaveURL(/\/my-patients$/);
  await expect(page.getByRole("row", { name: new RegExp(mine) })).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(colleagues) })).toHaveCount(0);

  // Back to Owner: the owner's menu again, and the choice is remembered on reload.
  await page.getByRole("group", { name: "View" }).getByText("Owner", { exact: true }).click();
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Team" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("group", { name: "View" }).getByRole("radio", { name: "Owner" })).toBeChecked();
});

test("FR-UX-06 failure path: an owner without a doctor profile has no switch, and My patients says why", async ({
  page,
}) => {
  await signInAs(page, OWNER);
  await home(page);
  await expect(page.getByRole("group", { name: "View" })).toHaveCount(0);

  await page.goto("/my-patients");
  // Next's route announcer is also an alert; this is the page's own.
  await expect(page.getByRole("alert").filter({ hasText: "doctor profile" })).toContainText(
    "You have no doctor profile in this clinic.",
  );
});
