import { expect, test, type Page } from "@playwright/test";

import { expectAccessible, issuedLink, noHorizontalScroll, signInWithGoogle } from "./portal-support";
import { DESK, signInAs } from "./queue-support";

/**
 * M7a (FR-AI-01, 02, 04): journey 1, the patient assistant explains a chosen prescription from its
 * database record, and an advice question gets the fixed referral; the staff assistant answers
 * with the clinic's own data. The stack's model is the console adapter (no provider, no network).
 */

test.use({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });

export async function linkedPatient(page: Page, request: Parameters<typeof issuedLink>[0], name: string): Promise<void> {
  const rxPath = await issuedLink(request);
  await signInWithGoogle(page, `${name}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`);
  await page.goto(`/portal/link/prescription/${rxPath.replace("/p/", "")}`);
  await page.getByLabel("Last 4 digits of your phone number").fill("0101");
  await page.getByRole("button", { name: "Save to my MediEase" }).click();
  await expect(page.getByRole("heading", { name: "Linked" })).toBeVisible();
}

async function ask(page: Page, text: string): Promise<void> {
  await page.getByLabel("Your message").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

test("journey 1 (M7a): the assistant explains the chosen prescription and refers advice", async ({ page, request }) => {
  await linkedPatient(page, request, "assistant");
  await page.goto("/portal");
  await page.getByRole("link", { name: "Ask the assistant" }).click();
  await expect(page).toHaveURL(/\/portal\/assistant$/);
  await expect(page.getByRole("heading", { name: "Assistant", level: 1 })).toBeVisible();

  const picker = page.getByRole("combobox");
  await picker.selectOption({ index: 1 });
  await ask(page, "When do I take my medicine?");
  const conversation = page.getByRole("list", { name: "Conversation" });
  await expect(conversation).toContainText("Syrup X");
  await expect(conversation).toContainText("5 ml");
  await expect(conversation).toContainText("Twice a day, morning and night, after food");

  await ask(page, "Should I double the dose?");
  await expect(conversation).toContainText("I can't give medical advice");
  await noHorizontalScroll(page);
  await expectAccessible(page);
});

test("M7a-P5: the staff assistant shows today's queue", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await context.newPage();
  await signInAs(page, DESK);
  await page.getByRole("navigation").getByRole("link", { name: "Assistant" }).click();
  await expect(page).toHaveURL(/\/assistant$/);
  await page.getByLabel("Message").fill("show today's queue");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("list", { name: "Conversation" })).toContainText("Queue for");
  await context.close();
});
