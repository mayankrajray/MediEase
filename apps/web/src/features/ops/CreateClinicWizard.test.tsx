import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { CLINIC_A, ops } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { replace, resetNavigation } from "@/test/navigation";

import { CreateClinicWizard } from "./CreateClinicWizard";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const DETAIL = `GET /api/v1/ops/clinics/${CLINIC_A}`;
const DOCTORS = `POST /api/v1/ops/clinics/${CLINIC_A}/doctors`;
const INVITES = `POST /api/v1/ops/clinics/${CLINIC_A}/staff-invites`;
const ACCEPT_URL = "http://localhost:3000/invite/secret-token-123";

const STARTED = "2026-10-03T09:00:00+00:00";
const NOW = new Date("2026-10-03T09:12:30+00:00"); // 12 whole minutes after STARTED

const clinic = (overrides: Record<string, unknown> = {}) => ({
  id: CLINIC_A,
  name: "Sample Clinic Three",
  slug: "sample-clinic-three",
  timezone: "Asia/Kolkata",
  status: "ONBOARDING",
  phone_e164: null,
  address_line: null,
  city: null,
  state: null,
  pincode: null,
  specialties: [],
  ...overrides,
});

const detail = (overrides: Record<string, unknown> = {}) =>
  json(200, {
    ...clinic(),
    onboarding: {
      started_at: STARTED,
      clinic_created_at: STARTED,
      doctors_added_at: null,
      staff_invited_at: null,
      patients_imported_at: null,
      first_appointment_at: null,
      first_prescription_at: null,
    },
    doctor_count: 0,
    staff: [],
    ...overrides,
  });

const doctor = (name = "Dr. Sample Doctor") => ({
  id: "d-1",
  user_id: null,
  display_name: name,
  qualification: "MBBS",
  registration_number: "SAMPLE-9",
  registration_council: "Sample State Medical Council",
  specialty: null,
  is_active: true,
});

const invitation = (overrides: Record<string, unknown> = {}) => ({
  membership_id: "m-1",
  user_id: "u-9",
  full_name: "Sample Owner Person",
  role: "OWNER",
  status: "INVITED",
  accept_url: ACCEPT_URL,
  ...overrides,
});

const base = {
  "GET /api/v1/me": () => json(200, ops()),
};

function renderWizard(resumeClinicId?: string) {
  return render(
    <SessionProvider>
      <CreateClinicWizard {...(resumeClinicId === undefined ? {} : { resumeClinicId })} />
    </SessionProvider>,
  );
}

function type(label: string | RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

const click = (name: string | RegExp) => fireEvent.click(screen.getByRole("button", { name }));

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
});

afterEach(() => {
  vi.useRealTimers();
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

async function createClinicStep() {
  type(/^Clinic name/, "Sample Clinic Three");
  click("Create clinic and continue");
  await screen.findByRole("heading", { name: /Step 2 of 3/ });
}

describe("Create clinic wizard", () => {
  it("R4, D2: sends the patient code prefix in capitals when given, and null when left empty", async () => {
    const api = mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () => json(201, clinic({ patient_code_prefix: "TQ" })),
      [DETAIL]: () => detail(),
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });

    type(/^Clinic name/, "Sample Clinic Three");
    type(/^Patient code prefix/, "tq");
    expect(screen.getByLabelText(/^Patient code prefix/)).toHaveValue("TQ");
    click("Create clinic and continue");
    await screen.findByRole("heading", { name: /Step 2 of 3/ });

    const created = api.calls.find((c) => c.method === "POST" && c.path === "/api/v1/ops/clinics");
    expect(created?.body).toMatchObject({ patient_code_prefix: "TQ" });
  });

  it("R4: a prefix the API refuses is shown on its field", async () => {
    mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () =>
        apiError(422, "REQ_VALIDATION_FAILED", "Some fields are missing or not valid.", {}, {
          fields: [{ field: "patient_code_prefix", reason: "must be 2-4 upper-case letters" }],
        }),
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });

    type(/^Clinic name/, "Sample Clinic Three");
    type(/^Patient code prefix/, "Q");
    click("Create clinic and continue");

    expect(await screen.findByText("must be 2-4 upper-case letters")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Patient code prefix/)).toHaveAttribute("aria-invalid", "true");
  });

  it("FR-OPS-01: walks clinic → doctors → owner invitation and shows the link once", async () => {
    const api = mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () => json(201, clinic()),
      [DETAIL]: () => detail(),
      [DOCTORS]: () => json(201, doctor()),
      [INVITES]: () => json(201, invitation()),
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderWizard();

    // Step 1: the URL name is suggested from the clinic name.
    expect(await screen.findByRole("heading", { name: "Create clinic" })).toBeInTheDocument();
    expect(screen.getByText(/1\. Clinic/)).toHaveAttribute("aria-current", "step");
    type(/^Clinic name/, "Sample Clinic Three");
    expect(screen.getByLabelText(/^Clinic URL name/)).toHaveValue("sample-clinic-three");
    type(/^Specialties/, "General Medicine, Paediatrics");
    click("Create clinic and continue");

    // Step 2: the elapsed time comes from the checklist's started_at.
    const step2 = await screen.findByRole("heading", { name: /Step 2 of 3/ });
    await act(async () => {}); // the focus moves in an effect after the step renders
    expect(step2).toHaveFocus();
    expect(await screen.findByText("12 min")).toBeInTheDocument();
    expect(screen.getByText(/1\. Clinic/)).toHaveTextContent("(done)");
    expect(screen.getByText(/2\. Doctors/)).toHaveAttribute("aria-current", "step");
    const created = api.calls.find((c) => c.method === "POST" && c.path === "/api/v1/ops/clinics");
    expect(created?.body).toEqual({
      name: "Sample Clinic Three",
      slug: "sample-clinic-three",
      timezone: "Asia/Kolkata",
      phone: null,
      address_line: null,
      city: null,
      state: null,
      pincode: null,
      specialties: ["General Medicine", "Paediatrics"],
      patient_code_prefix: null,
    });

    type(/^Doctor's name/, "Dr. Sample Doctor");
    type(/^Qualification/, "MBBS");
    type(/^Registration number/, "SAMPLE-9");
    type(/^Medical council/, "Sample State Medical Council");
    click("Add doctor");
    expect(await screen.findByText(/Dr\. Sample Doctor, MBBS \(registration SAMPLE-9\)/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Doctor's name/)).toHaveValue("");
    expect(api.calls.find((c) => c.path.endsWith("/doctors"))?.body).toMatchObject({
      display_name: "Dr. Sample Doctor",
      registration_council: "Sample State Medical Council",
      specialty: null,
    });
    click("Continue to owner invitation");

    // Step 3: invite the owner; the link appears once and can be copied.
    const step3 = await screen.findByRole("heading", { name: /Step 3 of 3/ });
    await act(async () => {}); // the focus moves in an effect after the step renders
    expect(step3).toHaveFocus();
    type("Full name (required)", "Sample Owner Person");
    expect(screen.getByLabelText("Role")).toHaveValue("OWNER");
    type("Email", "owner@sample-clinic.example");
    click("Create invitation");

    const link = await screen.findByLabelText(/Invitation link for Sample Owner Person/);
    expect(link).toHaveValue(ACCEPT_URL);
    expect(screen.getByText("only now")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(ACCEPT_URL));
    expect(await screen.findByText("Link copied.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.path.endsWith("/staff-invites"))?.body).toEqual({
      full_name: "Sample Owner Person",
      role: "OWNER",
      email: "owner@sample-clinic.example",
      phone: null,
    });

    // Finish: the summary never repeats the secret.
    click("Finish");
    expect(await screen.findByRole("heading", { name: /Clinic created/ })).toBeInTheDocument();
    expect(screen.getByText(/is created with 1 doctor and 1 invitation/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to the clinics" })).toHaveAttribute("href", "/ops");
    expect(document.body).not.toHaveTextContent("secret-token-123");
    expect(screen.queryByLabelText(/Invitation link/)).not.toBeInTheDocument();
  });

  it("FR-ORG-01: a taken URL name is reported on its field, with focus", async () => {
    mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () =>
        apiError(409, "CLN_SLUG_TAKEN", "That clinic URL is already taken. Choose another."),
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });

    type(/^Clinic name/, "Sample Clinic");
    click("Create clinic and continue");

    const slug = await screen.findByLabelText(/^Clinic URL name/);
    await waitFor(() => expect(slug).toHaveFocus());
    expect(slug).toHaveAttribute("aria-invalid", "true");
    expect(slug).toHaveAccessibleDescription(/already taken/);
    expect(screen.getByText(/1\. Clinic/)).toHaveAttribute("aria-current", "step");
  });

  it("field problems from the API land next to their fields", async () => {
    mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () =>
        apiError(422, "REQ_VALIDATION_FAILED", "Some fields are missing or not valid.", {}, {
          fields: [
            { field: "name", reason: "String should have at least 1 character" },
            { field: "pincode", reason: "pincode: must be 6 digits" },
          ],
        }),
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });

    click("Create clinic and continue");

    const name = await screen.findByLabelText(/^Clinic name/);
    expect(name).toHaveAccessibleDescription(/at least 1 character/);
    expect(screen.getByLabelText("Pincode")).toHaveAccessibleDescription(/6 digits/);
    await waitFor(() => expect(name).toHaveFocus());
  });

  it("I3: a doctor's missing registration details come back as field errors", async () => {
    mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () => json(201, clinic()),
      [DETAIL]: () => detail(),
      [DOCTORS]: () =>
        apiError(422, "REQ_VALIDATION_FAILED", "Some fields are missing or not valid.", {}, {
          fields: [{ field: "registration_number", reason: "Field required" }],
        }),
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });
    await createClinicStep();

    type(/^Doctor's name/, "Dr. Sample Doctor");
    click("Add doctor");

    const field = await screen.findByLabelText(/^Registration number/);
    expect(field).toHaveAccessibleDescription(/Field required/);
  });

  it("the doctors step can be skipped, with a reminder that prescriptions need one", async () => {
    mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () => json(201, clinic()),
      [DETAIL]: () => detail(),
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });
    await createClinicStep();

    expect(screen.getByText(/Prescriptions need a registered doctor/)).toBeInTheDocument();
    click("Skip for now");

    expect(await screen.findByRole("heading", { name: /Step 3 of 3/ })).toBeInTheDocument();
  });

  it("an invitation needs an email or a phone: nothing is sent without one", async () => {
    const api = mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () => json(201, clinic()),
      [DETAIL]: () => detail(),
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });
    await createClinicStep();
    click("Skip for now");
    await screen.findByRole("heading", { name: /Step 3 of 3/ });

    type("Full name (required)", "Sample Owner Person");
    click("Create invitation");

    const email = await screen.findByLabelText("Email");
    expect(email).toHaveAccessibleDescription(/email address or a phone number/);
    expect(api.count(INVITES)).toBe(0);
  });

  it("a phone alone is enough, and more people can be invited", async () => {
    const api = mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () => json(201, clinic()),
      [DETAIL]: () => detail(),
      [INVITES]: [
        () => json(201, invitation()),
        () => json(201, invitation({ membership_id: "m-2", full_name: "Sample Desk Person", role: "FRONT_DESK" })),
      ],
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });
    await createClinicStep();
    click("Skip for now");
    await screen.findByRole("heading", { name: /Step 3 of 3/ });

    type("Full name (required)", "Sample Owner Person");
    type("Phone", "9000000001");
    click("Create invitation");
    await screen.findByLabelText(/Invitation link for Sample Owner Person/);
    click("Invite another person");

    expect(await screen.findByText(/Invited so far \(1\)/)).toBeInTheDocument();
    expect(screen.getByLabelText("Role")).toHaveValue("DOCTOR");
    expect(screen.queryByLabelText(/Invitation link/)).not.toBeInTheDocument();
    type("Full name (required)", "Sample Desk Person");
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "FRONT_DESK" } });
    type("Phone", "9000000003");
    click("Create invitation");

    expect(await screen.findByLabelText(/Invitation link for Sample Desk Person/)).toBeInTheDocument();
    const bodies = api.calls.filter((c) => c.path.endsWith("/staff-invites")).map((c) => c.body);
    expect(bodies[0]).toMatchObject({ phone: "9000000001", email: null });
    expect(bodies[1]).toMatchObject({ role: "FRONT_DESK" });
  });

  it("if the clipboard is refused the link is selected for Ctrl+C", async () => {
    mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () => json(201, clinic()),
      [DETAIL]: () => detail(),
      [INVITES]: () => json(201, invitation()),
    });
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")) },
      configurable: true,
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });
    await createClinicStep();
    click("Skip for now");
    await screen.findByRole("heading", { name: /Step 3 of 3/ });
    type("Full name (required)", "Sample Owner Person");
    type("Email", "owner@sample-clinic.example");
    click("Create invitation");
    await screen.findByLabelText(/Invitation link/);

    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));

    expect(await screen.findByText(/press Ctrl\+C/)).toBeInTheDocument();
  });

  it("R7: a session that ends mid-wizard sends the person to sign in", async () => {
    window.history.replaceState(null, "", "/ops/clinics/new");
    mockApi({
      ...base,
      "POST /api/v1/ops/clinics": () => apiError(403, "AUTH_ACCOUNT_DISABLED", "Account disabled"),
    });
    renderWizard();
    await screen.findByRole("heading", { name: "Create clinic" });

    type(/^Clinic name/, "Sample Clinic");
    click("Create clinic and continue");

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fops%2Fclinics%2Fnew&reason=account_disabled"),
    );
  });
});

describe("Create clinic wizard: continuing a clinic that is still being set up", () => {
  it("FR-OPS-01: opens at the doctors step with what already exists", async () => {
    mockApi({
      ...base,
      [DETAIL]: () =>
        detail({
          doctor_count: 2,
          staff: [
            { membership_id: "m-7", user_id: "u-7", full_name: "Sample Owner Person", role: "OWNER", status: "INVITED" },
            { membership_id: "m-8", user_id: "u-8", full_name: "Already Active", role: "FRONT_DESK", status: "ACTIVE" },
          ],
        }),
    });

    renderWizard(CLINIC_A);

    expect(await screen.findByRole("heading", { name: /Sample Clinic Three: Step 2 of 3/ })).toBeInTheDocument();
    expect(screen.getByText("2 added earlier")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue to owner invitation" })).toBeInTheDocument();
    expect(await screen.findByText("12 min")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue to owner invitation" }));
    expect(await screen.findByText(/Invited so far \(1\)/)).toBeInTheDocument();
    expect(screen.queryByText(/Already Active/)).not.toBeInTheDocument();
  });

  it("a clinic that is already active cannot be continued", async () => {
    mockApi({ ...base, [DETAIL]: () => detail({ status: "ACTIVE" }) });

    renderWizard(CLINIC_A);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Sample Clinic Three is already set up");
    expect(screen.getByRole("link", { name: "Back to the clinics" })).toHaveAttribute("href", "/ops");
  });

  it("an unknown clinic shows the API's message with its Ref", async () => {
    mockApi({ ...base, [DETAIL]: () => apiError(404, "REQ_NOT_FOUND", "Clinic not found.") });

    renderWizard(CLINIC_A);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Clinic not found.");
    expect(within(alert).getByText("test-ref")).toBeInTheDocument();
  });
});
