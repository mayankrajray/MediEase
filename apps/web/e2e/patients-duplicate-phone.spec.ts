/**
 * TESTING.md §3, from M2: register a patient with a phone the clinic already has,
 * then choose the existing patient, or register a new family member.
 *
 * Uses `make seed` data only: the front desk of sample-clinic and the Rao family on
 * +91 90000 00101 (docs/RUNBOOK.md §1). Each run adds one more synthetic family
 * member with a unique name, so it can run again on the same database.
 */

import { expect, test, type Page } from "@playwright/test";

const DESK = "desk@sample-clinic.example";
const PASSWORD = process.env.E2E_PASSWORD ?? "MediEase-demo-2026";
const FAMILY_PHONE = "90000 00101";

async function signInAsFrontDesk(page: Page) {
  await page.goto("/sign-in");
  await page.getByLabel("Email or phone number").fill(DESK);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/queue$/);
}

async function fillRegistration(page: Page, fullName: string) {
  await page.getByRole("banner").getByRole("button", { name: "Register patient" }).click();
  const drawer = page.getByRole("dialog", { name: "Register patient" });
  await drawer.getByLabel(/^Full name/).fill(fullName);
  await drawer.getByLabel("Date of birth", { exact: true }).fill("1995-01-20");
  await drawer.getByLabel(/^Phone/).fill(FAMILY_PHONE);
  await drawer.getByLabel("Sex").selectOption("MALE");
  await drawer.getByRole("button", { name: "Register patient" }).click();
  await expect(drawer.getByText("This phone number is already registered")).toBeVisible();
  return drawer;
}

test("FR-PAT-02: a phone the clinic already has offers the family, then registers a new member", async ({ page }) => {
  const newName = `Kiran Rao ${Date.now().toString(36)}`;
  await signInAsFrontDesk(page);

  // The phone belongs to the Rao family: choose an existing patient instead.
  let drawer = await fillRegistration(page, newName);
  await expect(drawer.getByText("Meera Rao")).toBeVisible();
  await drawer.getByRole("button", { name: /^Use this patient: Asha Rao/ }).click();
  await expect(page).toHaveURL(/\/patients\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: "Asha Rao" })).toBeVisible();

  // Same details again: this time it is another person on the family's phone.
  drawer = await fillRegistration(page, newName);
  await drawer.getByRole("button", { name: "Register as a new family member" }).click();
  await expect(page.getByRole("heading", { level: 1, name: newName })).toBeVisible();
  await expect(page.getByText(/^SC-\d{4,}$/)).toBeVisible();
  await expect(page.getByRole("link", { name: "+91 90000 00101" })).toBeVisible();

  // FR-PAT-04: the header search finds the new member by name, phone masked.
  await page.keyboard.press("/");
  await page.getByRole("combobox", { name: "Find a patient" }).fill(newName);
  const option = page.getByRole("option", { name: new RegExp(newName) });
  await expect(option).toContainText("+91******0101");
});
