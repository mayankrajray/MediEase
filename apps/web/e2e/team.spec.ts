import { expect, test } from "@playwright/test";

import { linkPath, waitForEmail } from "./mailpit";
import { OWNER, signInAs } from "./queue-support";

/**
 * M6a-P5 (FR-ORG-07): the owner's Team page. The invitation is emailed by the worker into
 * Mailpit and accepted from its link; role changes and deactivation happen in dialogs.
 */

const MEMBER_PASSWORD = "a-team-member-synthetic-pass";

test("M6a-P5: the owner invites by email, the person joins from the link, then is moved and deactivated", async ({
  browser,
  page,
  request,
}) => {
  const n = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  const name = `Team Desk ${n}`;
  const email = `team.desk.${n}@example.test`;

  await signInAs(page, OWNER);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Team" }).click();
  await expect(page).toHaveURL(/\/team$/);
  await expect(page.getByRole("heading", { level: 1, name: "Team" })).toBeVisible();

  await page.getByRole("button", { name: "Invite someone" }).click();
  const drawer = page.getByRole("dialog", { name: "Invite someone" });
  await drawer.getByLabel(/Full name/).fill(name);
  await drawer.getByLabel("Role").selectOption("FRONT_DESK");
  await drawer.getByLabel("Email").fill(email);
  await drawer.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Invitation emailed to t\*\*\*@example\.test/ })).toBeVisible();
  const row = page.getByRole("row", { name: new RegExp(name) });
  await expect(row).toContainText("Invited");

  // The person accepts from the emailed link in their own browser and lands on Today.
  const member = await browser.newContext();
  const memberPage = await member.newPage();
  const text = await waitForEmail(request, email, "on MediEase");
  await memberPage.goto(linkPath(text, "/invite"));
  await memberPage.getByLabel("Choose a password").fill(MEMBER_PASSWORD);
  await memberPage.getByLabel("Type it again").fill(MEMBER_PASSWORD);
  await memberPage.getByRole("button", { name: "Set password and join" }).click();
  await expect(memberPage).toHaveURL(/\/today$/);

  // The owner sees them active, gives them the Doctor role, then deactivates them.
  await page.reload();
  await expect(row).toContainText("Active");
  await row.getByRole("button", { name: `Change role of ${name}` }).click();
  const roleDialog = page.getByRole("dialog", { name: `Change ${name}'s role` });
  await roleDialog.getByRole("radio", { name: /^Doctor/ }).check();
  await roleDialog.getByRole("button", { name: "Save role" }).click();
  await expect(page.getByRole("status").filter({ hasText: `${name} is now Doctor.` })).toBeVisible();

  await row.getByRole("button", { name: `Deactivate ${name}` }).click();
  const confirm = page.getByRole("dialog", { name: `Deactivate ${name}?` });
  await confirm.getByRole("button", { name: "Deactivate" }).click();
  await expect(page.getByRole("status").filter({ hasText: `${name} is deactivated.` })).toBeVisible();
  await expect(row).toContainText("Deactivated");

  // Their next request is refused.
  const refused = await memberPage.request.get("/api/v1/clinic");
  expect(refused.status()).toBe(403);
  expect(((await refused.json()) as { error: { code: string } }).error.code).toBe("AUTH_ACCOUNT_DISABLED");
  await member.close();
});

test("M6a-P5: demoting the only owner shows the last-owner message", async ({ page }) => {
  await signInAs(page, OWNER);
  await page.goto("/team");
  const mine = page.getByRole("row", { name: /\(you\)/ });
  await mine.getByRole("button", { name: /^Change role of / }).click();
  const dialog = page.getByRole("dialog", { name: /role$/ });
  await dialog.getByRole("radio", { name: /^Front desk/ }).check();
  await expect(dialog.getByText(/You will lose this Team page/)).toBeVisible();
  await dialog.getByRole("button", { name: "Save role" }).click();
  await expect(dialog.getByRole("alert")).toContainText("A clinic needs at least one owner.");
  await expect(dialog.getByRole("alert")).toContainText("Ref:");
});
