import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import { apiError, json, mockApi } from "@/test/api";

import { ApplyForm, emptyDraft, formData, problemsFor, serverProblems, stepOf } from "./ApplyForm";
import { ConfirmApplication } from "./ConfirmApplication";
import { REPLY_PROMISE } from "./lists";

const URL = "POST /api/v1/public/applications";

function pdf(name = "certificate.pdf", size = 64): File {
  return new File([new Uint8Array(size)], name, { type: "application/pdf" });
}

beforeEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});
afterEach(() => vi.unstubAllGlobals());

function type(label: string | RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function next() {
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
}

/** A solo doctor through every step, up to the review. */
async function fillSolo() {
  render(<ApplyForm />);
  fireEvent.click(screen.getByRole("radio", { name: /A doctor with my own practice/ }));
  await next();
  type(/^Clinic name/, "Sample Applying Clinic");
  type(/^Address/, "7 Synthetic Lane");
  type(/^City/, "Pune");
  type(/^State/, "Maharashtra");
  type(/^PIN code/, "411001");
  type(/^Clinic phone/, "9000000124");
  fireEvent.click(screen.getByRole("checkbox", { name: "Family Medicine" }));
  await next();
  type(/^Owner's full name/, "Synthetic Owner");
  type(/^Owner's mobile number/, "9000000123");
  type(/^Owner's email/, "owner@example.test");
  await next();
  type(/^Name/, "Dr. Synthetic Owner");
  type(/^Qualification/, "MBBS");
  fireEvent.change(screen.getByLabelText(/^Medical council/), { target: { value: "Maharashtra Medical Council" } });
  type(/^Registration number/, "SYN-1");
  fireEvent.change(screen.getByLabelText(/^Registration certificate/), { target: { files: [pdf()] } });
  await next();
}

describe("the application form (M6c-P1; clinic-onboarding R1-R8, R23)", () => {
  it("D3: promises a reply within 2 working days before anything is filled", () => {
    render(<ApplyForm />);
    expect(screen.getByText(REPLY_PROMISE)).toBeInTheDocument();
    expect(REPLY_PROMISE).toContain("within 2 working days");
  });

  it("checks each step before going on and names what is missing", async () => {
    render(<ApplyForm />);
    await next();
    await next();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Enter the clinic's name.");
    expect(alert).toHaveTextContent("Choose at least one specialty.");
    expect(screen.getByLabelText(/^Clinic name/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("heading", { level: 1, name: "The clinic" })).toBeInTheDocument();
  });

  it("FR-ONB-01: a solo doctor sends one multipart request and is told to check their email", async () => {
    const api = mockApi({ [URL]: () => json(202, { reference: "MA-2026-0042", email_masked: "o***@example.test" }) });
    await fillSolo();
    expect(screen.getByRole("heading", { level: 1, name: "Check and send" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send application" }));

    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("o***@example.test");
    expect(screen.getByRole("status")).toHaveTextContent("MA-2026-0042");
    expect(screen.getByText(REPLY_PROMISE)).toBeInTheDocument();

    const init = api.fetchMock.mock.calls[0]?.[1];
    const body = init?.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
    const sent = JSON.parse(String(body.get("application"))) as Record<string, unknown>;
    expect(sent).toMatchObject({ kind: "SOLO_DOCTOR", owner_practises: true, pincode: "411001", specialties: ["Family Medicine"] });
    expect((sent["doctors"] as { is_owner: boolean }[])[0]?.is_owner).toBe(true);
    expect(body.get("certificate_1")).toBeInstanceOf(File);
    expect(sent).not.toHaveProperty("website");
  });

  it("R7: a file the API refuses brings the person back to that doctor", async () => {
    mockApi({
      [URL]: () => apiError(422, "ONB_FILE_REJECTED", "The certificate of doctor 1 must be a PDF, JPEG or PNG file.", {}, { position: "1", reason: "type" }),
    });
    await fillSolo();
    fireEvent.click(screen.getByRole("button", { name: "Send application" }));
    expect(await screen.findByRole("heading", { level: 1, name: "The doctors" })).toBeInTheDocument();
    expect(within(screen.getByRole("alert")).getByText("Use a PDF, JPEG or PNG file.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Registration certificate/)).toHaveAttribute("aria-invalid", "true");
  });

  it("R16: too many applications is said plainly", async () => {
    mockApi({ [URL]: () => apiError(429, "ONB_RATE_LIMITED", "Too many applications. Please try again later.", { "Retry-After": "3600" }) });
    await fillSolo();
    fireEvent.click(screen.getByRole("button", { name: "Send application" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Too many applications/);
  });

  it("a clinic adds doctors, marks the practising owner, and refuses large or wrong files before sending", () => {
    const draft = {
      ...emptyDraft(),
      owner_practises: true,
      doctors: [
        { name: "A", qualification: "MBBS", council: "Delhi Medical Council", registration_number: "1", is_owner: false, file: pdf("a.txt") },
        { name: "B", qualification: "MBBS", council: "Delhi Medical Council", registration_number: "2", is_owner: false, file: pdf("b.pdf", 5 * 1024 * 1024 + 1) },
      ],
    };
    expect(problemsFor("doctors", draft)).toEqual({
      doctors: "Mark which doctor is the owner.",
      "doctors.1.certificate": "Use a PDF, JPEG or PNG file.",
      "doctors.2.certificate": "The file must be at most 5 MB.",
    });
    const form = formData(draft);
    expect(form.get("certificate_1")).toBeInstanceOf(File);
    expect(form.get("certificate_2")).toBeInstanceOf(File);
  });

  it("maps the API's field names to steps and messages", () => {
    expect(stepOf("doctors.2.council")).toBe("doctors");
    expect(stepOf("owner_email")).toBe("owner");
    expect(stepOf("pincode")).toBe("clinic");
    const error = new ApiError("REQ_VALIDATION_FAILED", "x", 422, "r", { fields: [{ field: "specialties.0", reason: "is not on the list" }] });
    expect(serverProblems(error)).toEqual({ specialties: "Check this field: is not on the list." });
    expect(serverProblems(new Error("x"))).toBeUndefined();
  });
});

describe("confirming the application (M6c-P1; R11, R12)", () => {
  it("opening the page changes nothing; the button confirms and promises the reply", async () => {
    const api = mockApi({ "POST /api/v1/public/applications/confirm": () => json(200, { reference: "MA-2026-0042" }) });
    render(<ConfirmApplication token="tok-1" />);
    expect(api.calls).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Confirm my application" }));
    expect(await screen.findByRole("status")).toHaveTextContent("We received application MA-2026-0042");
    expect(screen.getByText(REPLY_PROMISE)).toBeInTheDocument();
    expect(api.calls[0]?.body).toEqual({ token: "tok-1" });
  });

  it("an unknown, used or expired link says so with one message", async () => {
    mockApi({ "POST /api/v1/public/applications/confirm": () => apiError(404, "ONB_CONFIRM_INVALID", "This link is not valid any more.") });
    render(<ConfirmApplication token="old" />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm my application" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("This link is not valid any more."));
    expect(screen.getByRole("link", { name: "apply again" })).toHaveAttribute("href", "/apply");
  });
});
