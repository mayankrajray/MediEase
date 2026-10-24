import { expect, test } from "@playwright/test";

import { DESK, newPatient, signInAs } from "./queue-support";

/**
 * M6b-P1 (FR-PRT-06 b, FR-PRT-02): the front desk invites a patient from the profile; a new
 * patient account opens the invitation, signs up on the way, links the record and sees the
 * clinic. Failure path: the used invitation says it is no longer valid.
 */

const PASSWORD = "a-synthetic-patient-pass";

test("M6b-P1: staff invite a patient, a new account links, and a used invite is no longer valid", async ({
  page,
  browser,
  request,
}) => {
  const patient = await newPatient(request, "Leela");
  const firstName = patient.name.split(" ")[0] ?? "";

  // The front desk invites from the patient's profile; the link is shown once.
  await signInAs(page, DESK);
  await page.goto(`/patients/${patient.id}`);
  const card = page.getByRole("region", { name: "Patient app" });
  await expect(card.getByText(/^Not linked/)).toBeVisible();
  await card.getByRole("button", { name: "Invite to the patient app" }).click();
  const field = card.getByTestId("portal-invite-link");
  await expect(field).toHaveValue(/\/portal\/link\//);
  await expect(card.getByRole("img", { name: /QR code/ })).toBeVisible();
  await expect(card.getByText(/^Invited, link expires/)).toBeVisible();
  const invitePath = new URL(await field.inputValue()).pathname;

  // The patient, signed out, opens the link at 360 px, creates an account and comes back to it.
  const context = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const phone = await context.newPage();
  await phone.goto(invitePath);
  await expect(phone).toHaveURL(/\/portal\/sign-in\?next=/);
  await phone.getByRole("link", { name: "Create an account" }).click();
  await phone.getByLabel("Your name").fill(`${firstName} Patient`);
  await phone.getByLabel("Email").fill(`leela.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`);
  await phone.getByLabel("Password").fill(PASSWORD);
  await phone.getByRole("button", { name: "Create account" }).click();

  await expect(phone).toHaveURL(new RegExp(`${invitePath}$`));
  await expect(phone.getByRole("heading", { name: "Link your records at Sample Clinic" })).toBeVisible();
  await expect(phone.getByText(new RegExp(`^${firstName} ·`))).toBeVisible();
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await phone.getByRole("button", { name: "Link", exact: true }).click();
  await expect(phone.getByRole("heading", { name: "Linked" })).toBeVisible();

  // The account lists the clinic, through the portal API.
  await phone.getByRole("link", { name: "Go to your account" }).click();
  await expect(phone.getByRole("list", { name: "Linked clinics" })).toContainText(`Sample Clinic · ${firstName}`);

  // Failure path: the invitation was used.
  await phone.goto(invitePath);
  await expect(phone.getByRole("heading", { name: "This invitation is no longer valid" })).toBeVisible();
  await context.close();

  // The front desk sees the link on the profile.
  await page.reload();
  await expect(page.getByRole("region", { name: "Patient app" }).getByText(/^Linked by invite since/)).toBeVisible();
});
