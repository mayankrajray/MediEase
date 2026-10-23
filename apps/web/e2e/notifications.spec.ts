import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { DESK, DOCTOR, newPatient, sessionRunningNow, signInApi, signInAs } from "./queue-support";

/**
 * M6a-P7 (FR-NTF-02, 03, 05): the desk books with the sample doctor, the doctor's bell shows it
 * within one summary poll (15 s), the notification names the patient by first name and code and
 * opens the queue on its day, and reading it clears it. Failure path: with "A patient is booked
 * with me" turned off, a booking adds nothing. Uses `make seed` (RUNBOOK §1).
 */

const DOCTOR_NAME = "Dr. Sample Doctor";
const BOOKED_LABEL = "A patient is booked with me";

const bell = (page: Page) => page.getByRole("banner").getByRole("button", { name: /^Notifications/ });

async function book(request: APIRequestContext, label: string): Promise<string> {
  const { sessionId } = await sessionRunningNow(request, { doctorName: DOCTOR_NAME });
  const patient = await newPatient(request, label);
  const token = await signInApi(request, DESK);
  const resp = await request.post("/api/v1/appointments", {
    headers: { "X-CSRF-Token": token },
    data: { session_id: sessionId, patient_id: patient.id },
  });
  expect(resp.status(), await resp.text()).toBe(201);
  return patient.name.split(" ")[0] ?? label;
}

/** Opens the drawer, marks everything read when anything is unread, and closes it. */
async function clearAll(page: Page): Promise<void> {
  await bell(page).click();
  const drawer = page.getByRole("dialog", { name: "Notifications" });
  await expect(drawer.getByText("No notifications yet").or(drawer.getByRole("list", { name: "Latest notifications" }))).toBeVisible();
  const markAll = drawer.getByRole("button", { name: "Mark all as read" });
  if (await markAll.isVisible()) {
    await markAll.click();
    await expect(drawer.getByText("All notifications marked as read.")).toBeAttached();
  }
  await drawer.getByRole("button", { name: "Close" }).click();
  await expect(bell(page)).toHaveAccessibleName("Notifications");
}

async function setBookedNotice(page: Page, on: boolean): Promise<void> {
  await page.goto("/settings/notifications");
  const box = page.getByRole("checkbox", { name: BOOKED_LABEL });
  await expect(box).toBeVisible();
  if ((await box.isChecked()) !== on) {
    await box.click();
    await expect(page.getByRole("status").filter({ hasText: `is ${on ? "on" : "off"}` })).toBeVisible();
  }
  await expect(box).toBeChecked({ checked: on });
}

test("FR-NTF-03: a desk booking lights the doctor's bell, opens the queue on its day and clears once read", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000);
  await signInAs(page, DOCTOR);
  await setBookedNotice(page, true);
  await clearAll(page);

  const first = await book(request, "Notify");

  // One summary poll later (15 s), without reloading.
  await expect(bell(page)).toHaveAccessibleName(/^Notifications, \d+ unread$/, { timeout: 25_000 });
  await bell(page).click();
  const drawer = page.getByRole("dialog", { name: "Notifications" });
  const item = drawer.getByRole("link", { name: new RegExp(`Unread: ${first} · \\S+ booked for `) });
  await expect(item).toBeVisible();
  await expect(drawer).not.toContainText(/complaint|diagnos/i);

  await item.click();
  await expect(page).toHaveURL(/\/queue\?date=\d{4}-\d{2}-\d{2}$/);
  await expect(page.getByRole("heading", { level: 1, name: "Today's queue" })).toBeVisible();
  await expect(bell(page)).toHaveAccessibleName("Notifications");
});

test("FR-NTF-05: with bookings turned off, a booking adds nothing to the doctor's bell", async ({ page, request }) => {
  test.setTimeout(120_000);
  await signInAs(page, DOCTOR);
  await setBookedNotice(page, false);
  try {
    await clearAll(page);
    const muted = await book(request, "Muted");

    await page.reload();
    await expect(bell(page)).toHaveAccessibleName("Notifications");
    await bell(page).click();
    const drawer = page.getByRole("dialog", { name: "Notifications" });
    await expect(drawer.getByText("No notifications yet").or(drawer.getByRole("list", { name: "Latest notifications" }))).toBeVisible();
    await expect(drawer).not.toContainText(`${muted} ·`);
  } finally {
    await setBookedNotice(page, true);
  }
});
