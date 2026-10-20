/**
 * AC4 (FR-QUE-03): two browsers on the queue; when one marks a patient arrived, the other shows
 * it without a reload. Screens poll every 5 s, so the worst case is one interval plus the request;
 * the assertion allows 6 s. Setup as in booking-three-interactions.spec.ts.
 */

import { expect, test, type Browser, type Page } from "@playwright/test";

import { DESK, DOCTOR, newPatient, openQueue, sessionRunningNow, signInApi, signInAs } from "./queue-support";

async function boardAs(browser: Browser, email: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  // M6-P1: every member lands on Today; the queue is one click away.
  await signInAs(page, email);
  await openQueue(page);
  return page;
}

test("AC4: a patient marked arrived on one screen shows on the other within one poll", async ({ browser, request }) => {
  const { sessionId } = await sessionRunningNow(request);
  const patient = await newPatient(request, "Ira");
  const token = await signInApi(request, DESK);
  const booked = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": token },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(booked.status(), await booked.text()).toBe(201);

  const desk = await boardAs(browser, DESK);
  const doctor = await boardAs(browser, DOCTOR);
  const onDoctor = doctor.getByRole("row").filter({ hasText: patient.name });
  await expect(onDoctor).toContainText("Booked");

  await desk.getByRole("button", { name: `Mark ${patient.name} arrived` }).click();
  await expect(desk.getByRole("status").filter({ hasText: `${patient.name} marked arrived` })).toBeVisible();

  const clicked = Date.now();
  await expect(onDoctor).toContainText("Arrived", { timeout: 6_000 });
  expect(Date.now() - clicked).toBeLessThan(6_000);
  await expect(doctor.getByRole("button", { name: `Start ${patient.name}'s consultation` })).toBeVisible();
});
