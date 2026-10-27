/**
 * Set-up for the upload journeys (M7b): an issued sample linked to a fresh portal account through
 * its prescription link and the patient's last 4 digits (0101), as in the assistant journey.
 */

import { expect, type APIRequestContext, type Page } from "@playwright/test";

import { issuedPrescription, type IssuedPrescription, signInWithGoogle } from "./portal-support";

export async function linkedPatientFor(page: Page, request: APIRequestContext, email: string): Promise<IssuedPrescription> {
  const rx = await issuedPrescription(request);
  await signInWithGoogle(page, email);
  await page.goto(`/portal/link/prescription/${rx.linkPath.replace("/p/", "")}`);
  await page.getByLabel("Last 4 digits of your phone number").fill("0101");
  await page.getByRole("button", { name: "Save to my MediEase" }).click();
  await expect(page.getByRole("heading", { name: "Linked" })).toBeVisible();
  return rx;
}
