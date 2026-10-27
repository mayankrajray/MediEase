import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { linkedPatientFor } from "./upload-support";
import { expectAccessible, issuedPrescription, noHorizontalScroll, SAMPLE, signInWithGoogle } from "./portal-support";
import { DOCTOR, signInApi } from "./queue-support";

/**
 * M7b (FR-UPL-01..05, NFR-20): journeys 2-5 on the real stack: the upload worker, ClamAV and the
 * identifier reader (QR and the PDF's text layer, no OCR). The model is the console adapter, which
 * explains a prescription only from the database page the API gives it.
 */

test.use({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });

const UPL = "/api/v1/portal/prescription-uploads";
/** The worker polls every 2 s, then ClamAV and the reader take a few seconds. */
const CHECKED = { timeout: 60_000 };

function email(name: string): string {
  return `${name}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`;
}

/** The issued version's PDF as the doctor prints it (layout 3: the code and the QR). */
async function pdfOf(request: APIRequestContext, rxId: string, clinicId: string): Promise<Buffer> {
  await signInApi(request, DOCTOR);
  const resp = await request.get(`/api/v1/prescriptions/${rxId}/pdf`, { headers: { "X-Clinic-ID": clinicId } });
  expect(resp.status(), await resp.text()).toBe(200);
  return resp.body();
}

async function uploadFile(page: Page, name: string, mimeType: string, buffer: Buffer): Promise<void> {
  await page.getByLabel("Photo or PDF of the prescription").setInputFiles({ name, mimeType, buffer });
  await page.getByRole("button", { name: "Upload" }).click();
}

async function ask(page: Page, text: string): Promise<void> {
  await page.getByLabel("Your message").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
}

test("journey 2 (M7b): a family member uploads a prescription; it is verified and explained from the record", async ({
  page,
  request,
}) => {
  const rx = await issuedPrescription(request);
  const pdf = await pdfOf(request, rx.rxId, rx.clinicId);
  await signInWithGoogle(page, email("family"));
  await page.goto("/portal/assistant");
  await expect(page.getByText(/The file is deleted once it is checked, and clinic staff never see it/)).toBeVisible();
  await uploadFile(page, "prescription.pdf", "application/pdf", pdf);

  // Not this account's record: the patient's last 4 digits (the synthetic phone ends in 0101).
  const digits = page.getByLabel("Last 4 digits of the patient's phone");
  await expect(digits).toBeVisible(CHECKED);
  await digits.fill("0101");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText(/^Verified: /)).toBeVisible();
  await expect(page.getByText(/It has not been added to your account/)).toBeVisible();

  await ask(page, "When do I give the medicine?");
  const conversation = page.getByRole("list", { name: "Conversation" });
  await expect(conversation).toContainText("Syrup X");
  await expect(conversation).toContainText("5 ml");
  await noHorizontalScroll(page);
  await expectAccessible(page);

  // Linking nothing: the family member's own records stay empty.
  const mine = await page.request.get("/api/v1/portal/prescriptions");
  expect(((await mine.json()) as { items: unknown[] }).items).toEqual([]);
});

test("journey 3 (M7b): an older version is never swapped silently; the assistant follows the user's choice", async ({
  page,
  request,
}) => {
  const rx = await linkedPatientFor(page, request, email("revised"));
  const oldPdf = await pdfOf(request, rx.rxId, rx.clinicId);
  // The doctor revises it: version 2 halves the dose.
  const headers = { "X-CSRF-Token": await signInApi(request, DOCTOR), "X-Clinic-ID": rx.clinicId };
  const draft = await request.post(`/api/v1/prescriptions/${rx.rxId}/revise`, { headers });
  expect(draft.status(), await draft.text()).toBe(201);
  const v2 = (await draft.json()) as { id: string; revision: number };
  const saved = await request.put(`/api/v1/prescriptions/${v2.id}`, {
    headers,
    data: { revision: v2.revision, items: [{ ...SAMPLE, dose: "2.5 ml" }], advice: { return_if: ["breathing is difficult"] } },
  });
  expect(saved.status(), await saved.text()).toBe(200);
  const issued = await request.post(`/api/v1/prescriptions/${v2.id}/issue`, { headers, data: { revision: v2.revision + 1 } });
  expect(issued.status(), await issued.text()).toBe(200);

  await page.goto("/portal/assistant");
  await uploadFile(page, "old.pdf", "application/pdf", oldPdf);
  const choice = page.getByRole("group", { name: /This is an older version \(version 1\)/ });
  await expect(choice).toBeVisible(CHECKED);

  await choice.getByRole("button", { name: /The one I uploaded/ }).click();
  await expect(page.getByText("The assistant will explain version 1.")).toBeVisible();
  await ask(page, "When do I take my medicine?");
  const conversation = page.getByRole("list", { name: "Conversation" });
  await expect(conversation).toContainText("older version");
  await expect(conversation).toContainText("5 ml");

  await choice.getByRole("button", { name: "The latest (version 2)" }).click();
  await expect(page.getByText("The assistant will explain version 2.")).toBeVisible();
  await ask(page, "When do I take my medicine now?");
  await expect(conversation).toContainText("2.5 ml"); // a new conversation for the new choice
  await expect(conversation).not.toContainText("older version");
});

test("journey 4 (M7b): another account's upload and prescription stay out of reach", async ({ page, request, browser }) => {
  const rx = await linkedPatientFor(page, request, email("owner"));
  await page.goto("/portal/assistant");
  await page.getByLabel("Verification code").fill(rx.rxId);
  await page.getByRole("button", { name: "Check code" }).click();
  await expect(page.getByText(/^Verified: /)).toBeVisible();
  const mine = (await (await page.request.post(`${UPL}/by-code`, {
    headers: { "X-CSRF-Token": await csrfOf(page) },
    data: { code: rx.rxId },
  })).json()) as { id: string };

  const other = await browser.newContext({ viewport: { width: 360, height: 740 } });
  const stranger = await other.newPage();
  await signInWithGoogle(stranger, email("stranger"));
  // The owner's upload, by its ID: not found, and not usable by the assistant.
  expect((await stranger.request.get(`${UPL}/${mine.id}`)).status()).toBe(404);
  const turn = await stranger.request.post("/api/v1/portal/assistant/turns", {
    headers: { "X-CSRF-Token": await csrfOf(stranger) },
    data: { messages: [{ role: "user", content: "explain" }], context: { upload_id: mine.id } },
  });
  expect(turn.status()).toBe(404);
  // The printed code alone grants nothing: the wrong digits are refused.
  await stranger.goto("/portal/assistant");
  await stranger.getByLabel("Verification code").fill(rx.rxId);
  await stranger.getByRole("button", { name: "Check code" }).click();
  await stranger.getByLabel("Last 4 digits of the patient's phone").fill("9999");
  await stranger.getByRole("button", { name: "Confirm" }).click();
  await expect(stranger.getByText("That did not match. 4 attempts left.")).toBeVisible();
  await expect(stranger.getByText(/^Verified: /)).toHaveCount(0);
  await other.close();
});

test("journey 5 (M7b): an infected file and an unreadable one are rejected, and the user can try again", async ({ page }) => {
  await signInWithGoogle(page, email("eicar"));
  await page.goto("/portal/assistant");
  await uploadFile(page, "infected.pdf", "application/pdf", eicarPdf());
  await expect(page.getByText("The file was refused by the safety check and deleted.")).toBeVisible(CHECKED);

  await uploadFile(page, "blank.png", "image/png", BLANK_PNG);
  await expect(page.getByText(/No MediEase code was found on it/)).toBeVisible(CHECKED);
  await expect(page.getByLabel("Photo or PDF of the prescription")).toBeVisible();

  // Not a PDF, JPEG or PNG: refused before anything is stored.
  await uploadFile(page, "notes.txt", "text/plain", Buffer.from("just text"));
  await expect(page.getByText("Upload a PDF, JPEG or PNG of at most 10 MB.")).toBeVisible();
});

async function csrfOf(page: Page): Promise<string> {
  const cookie = (await page.context().cookies()).find((c) => c.name === "me_pt_csrf");
  expect(cookie, "portal session").toBeDefined();
  return cookie?.value ?? "";
}

/** The EICAR test string, assembled here so no antivirus quarantines this file, in a PDF. */
function eicarPdf(): Buffer {
  const eicar = ["X5O!P%@AP[4\\PZX54(P^)7CC)7}$", "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!", "$H+H*"].join("");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R /Names << /EmbeddedFiles << /Names [(t.txt) 4 0 R] >> >> >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
    "<< /Type /Filespec /F (t.txt) /EF << /F 5 0 R >> >>",
    `<< /Type /EmbeddedFile /Length ${eicar.length} >>\nstream\n${eicar}\nendstream`,
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

/** A 64 x 64 white PNG: a valid image with no QR code on it. */
const BLANK_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAAAAACPAi4CAAAALElEQVR4nO3MoQEAAAjDMOD/n+GIGUTqm97KmvAHAAAAAAAAAAAAAAAA8B44UC0Bf7Sd28IAAAAASUVORK5CYII=",
  "base64",
);
