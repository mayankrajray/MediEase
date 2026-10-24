import { expect, test } from "@playwright/test";

import { bookPatient, bookableDays, uniqueWord } from "./p8-support";
import { DESK, OWNER, signInApi, signInAs } from "./queue-support";

/**
 * M6a-P8 (FR-AUD-03, FR-AUD-01, decision 8A): the front desk cancels a booking; the owner opens
 * *Audit log*, filters to Appointments and sees the cancellation by the front desk in words, then
 * exports CSV. Failure path: the front desk is told the log is for owners. Uses `make seed`.
 */

test("FR-AUD-03: the owner reads who cancelled what, and exports the log", async ({ page, request }) => {
  test.setTimeout(90_000);
  const { sessionId } = await bookableDays(request);
  const booked = await bookPatient(request, uniqueWord("Audit"), sessionId);
  const deskToken = await signInApi(request, DESK);
  const cancelled = await request.post(`/api/v1/appointments/${booked.id}/cancel`, {
    headers: { "X-CSRF-Token": deskToken },
    data: { reason: "PATIENT_REQUEST" },
  });
  expect(cancelled.status(), await cancelled.text()).toBe(200);

  await signInAs(page, OWNER);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Audit log" }).click();
  await expect(page).toHaveURL(/\/settings\/audit$/);
  await page.getByLabel("Category").selectOption("APPOINTMENTS");
  await page.getByRole("button", { name: "Show" }).click();

  const table = page.getByRole("table", { name: "Audit log entries, newest first" });
  const row = table.getByRole("row").filter({ hasText: "Cancelled an appointment" }).first();
  await expect(row).toContainText("Front desk");
  await expect(row).toContainText("cancel reason: PATIENT_REQUEST");
  await expect(table).not.toContainText("Registered a patient");

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toMatch(/^audit-sample-clinic-\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}\.csv$/);
  await expect(page.getByRole("status").filter({ hasText: "Exported" })).toBeVisible();
});

test("FR-AUD-03 failure path: the front desk is told the audit log is for owners", async ({ page }) => {
  await signInAs(page, DESK);
  await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Audit log" })).toHaveCount(0);
  await page.goto("/settings/audit");
  await expect(page.getByRole("alert").filter({ hasText: "for the clinic's owners" })).toBeVisible();
});
