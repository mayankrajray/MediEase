/**
 * AC6 (FR-APT-03): from the queue screen, the front desk books in at most three interactions:
 * Book → the patient → Confirm (the next token is already chosen). Typing the search text is not
 * counted as an interaction. Uses `make seed` data plus a session running now and a fresh
 * synthetic patient (queue-support.ts), so it passes at any hour and on a reused database.
 */

import { expect, test } from "@playwright/test";

import { DESK, newPatient, openQueue, sessionRunningNow, signInAs } from "./queue-support";

test("AC6: booking from the queue takes at most three interactions", async ({ page, request }) => {
  await sessionRunningNow(request);
  const patient = await newPatient(request, "Divya");
  await signInAs(page, DESK);
  await openQueue(page);
  await expect(page.getByRole("heading", { name: "Today's queue" })).toBeVisible();

  let interactions = 0;
  await page.getByRole("button", { name: "Book" }).click();
  interactions += 1;
  const drawer = page.getByRole("dialog", { name: "Book appointment" });
  await drawer.getByLabel("Patient").fill(patient.name); // typing: not an interaction
  await drawer.getByRole("button", { name: new RegExp(patient.name) }).click();
  interactions += 1;
  await expect(drawer.getByRole("radio", { checked: true })).toHaveCount(1);
  await drawer.getByRole("button", { name: "Confirm booking" }).click();
  interactions += 1;

  await expect(page.getByRole("status").filter({ hasText: `${patient.name} booked` })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: patient.name })).toContainText("Booked");
  expect(interactions).toBeLessThanOrEqual(3);
});
