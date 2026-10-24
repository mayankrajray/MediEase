import { expect, test } from "@playwright/test";

import { bookPatient, bookableDays, uniqueWord } from "./p8-support";
import { DESK, OWNER, signInApi, signInAs } from "./queue-support";

/**
 * M6a-P8 (FR-APT-09, decisions 6A, 7A): the owner adds leave on a day two patients are booked;
 * the front desk sees Today's tile, opens *Bookings to move*, moves one patient to the next day
 * and cancels the other as "Doctor unavailable", and both leave the list. The leave is removed
 * afterwards so the journey can run again. Uses `make seed` (RUNBOOK §1).
 */

test("FR-APT-09: leave over a booked day lists the bookings; the desk moves one and cancels the other", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  const { doctorId, day, next, sessionId } = await bookableDays(request);
  const mover = await bookPatient(request, uniqueWord("Mover"), sessionId);
  const stopper = await bookPatient(request, uniqueWord("Stopper"), sessionId);

  const ownerToken = await signInApi(request, OWNER);
  const leave = await request.post(`/api/v1/clinic/doctors/${doctorId}/schedule-exceptions`, {
    headers: { "X-CSRF-Token": ownerToken },
    data: { kind: "LEAVE", on_date: day, note: "e2e" },
  });
  expect(leave.status(), await leave.text()).toBe(201);
  const leaveId = ((await leave.json()) as { exception: { id: string } }).exception.id;

  try {
    await signInAs(page, DESK);
    const tile = page.getByRole("link", { name: /Bookings to move\s*\d+/ });
    await expect(tile).toBeVisible();
    await tile.click();
    await expect(page).toHaveURL(/\/bookings-to-move$/);
    const table = page.getByRole("table", { name: "Bookings to move, earliest first" });
    const moverRow = table.getByRole("row").filter({ hasText: `${mover.first} · ` });
    const stopperRow = table.getByRole("row").filter({ hasText: `${stopper.first} · ` });
    await expect(moverRow).toContainText("Doctor on leave");
    await expect(stopperRow).toContainText("Doctor on leave");

    // Move: the drawer opens on the closed day; the next day has room.
    await moverRow.getByRole("button", { name: /^Reschedule / }).click();
    const drawer = page.getByRole("dialog", { name: new RegExp(`^Reschedule ${mover.first}`) });
    await drawer.getByLabel("Date").fill(next);
    const place = drawer.getByRole("radio", { disabled: false }).first();
    await place.check();
    await drawer.getByRole("button", { name: "Confirm new time" }).click();
    await expect(page.getByRole("status").filter({ hasText: `${mover.first}` })).toContainText("moved");
    await expect(moverRow).toHaveCount(0);

    // Cancel: "Doctor unavailable" is already chosen (decision 7A tells the patient).
    await stopperRow.getByRole("button", { name: /^Cancel / }).click();
    const dialog = page.getByRole("dialog", { name: new RegExp(`Cancel ${stopper.first}`) });
    await expect(dialog.getByRole("radio", { name: "Doctor unavailable" })).toBeChecked();
    await dialog.getByRole("button", { name: "Cancel appointment" }).click();
    await expect(page.getByRole("status").filter({ hasText: "cancelled" })).toBeVisible();
    await expect(stopperRow).toHaveCount(0);
  } finally {
    const token = await signInApi(request, OWNER);
    await request.delete(`/api/v1/clinic/doctors/${doctorId}/schedule-exceptions/${leaveId}`, {
      headers: { "X-CSRF-Token": token },
    });
  }
});
