import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { navigation, replace, resetNavigation } from "@/test/navigation";

import { FindADoctor } from "./FindADoctor";
import { Home } from "./Home";
import { MyAppointments } from "./MyAppointments";
import { PortalAccountPage } from "./PortalAccountPage";
import { PortalPrescription, PortalPrescriptions } from "./PortalPrescriptions";
import { PortalShell } from "./PortalShell";
import { CLINIC_ID, link, me, OTHER_CLINIC_ID, PORTAL_ACCOUNT, renderPortal } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const HOUR = 3_600_000;
const later = new Date(Date.now() + 48 * HOUR);
const earlier = new Date(Date.now() - 72 * HOUR);

function appointment(id: string, start: Date, status = "BOOKED", extra: Record<string, unknown> = {}) {
  const end = new Date(start.getTime() + 3 * HOUR);
  return {
    id,
    doctor_name: "Dr. Mehta",
    on_date: start.toISOString().slice(0, 10),
    starts_at: start.toISOString(),
    session_starts_at: start.toISOString(),
    session_ends_at: end.toISOString(),
    mode: "SLOTS",
    slot_start: start.toISOString(),
    token_number: null,
    status,
    ...extra,
  };
}

function group(clinicId: string, name: string, appointments: unknown[]) {
  return { clinic_id: clinicId, clinic_name: name, timezone: "Asia/Kolkata", phone_e164: "+919000000010", appointments };
}

const RX = {
  id: "0192f0a0-0000-7000-8000-0000000000d1",
  clinic_id: CLINIC_ID,
  clinic_name: "Sample Clinic",
  doctor_name: "Dr. Mehta",
  version: 2,
  issued_at: "2026-10-20T05:30:00Z",
};

const PAGE = {
  language: "en",
  version: 1,
  clinic_name: "Sample Clinic",
  clinic_phone_e164: null,
  call_label: "Call the clinic",
  doctor_name: "Dr. Mehta",
  doctor_lines: [],
  issued_on: { label: "Date", value: "20 Oct 2026" },
  updated_note: null,
  medicines_heading: "Medicines",
  medicines: [{ number: 1, name: "Syrup X", form_strength: null, fields: [{ label: "How much", value: "5 ml" }] }],
  advice_heading: "Advice",
  advice: [],
  advice_notes: null,
  follow_up: null,
  schedule_heading: "Medicine schedule",
  schedule_columns: ["Morning", "Afternoon", "Evening", "Night"],
  schedule_as_written: "As the doctor wrote",
  schedule: [],
};

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  navigation.pathname = "/portal";
  document.cookie = "me_pt_csrf=portal-csrf; path=/";
});

afterEach(() => {
  document.cookie = "me_pt_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  document.cookie = "me_pt_lang=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("the portal shell (M6b-P2, R15, R21, R25)", () => {
  it("R15, M6b-P3 R36: five tabs, the current one marked", async () => {
    mockApi({ ...me(), "GET /api/v1/portal/links": () => json(200, { items: [] }) });
    await renderPortal(<Home />);
    const nav = screen.getByRole("navigation", { name: "Patient app" });
    expect(within(nav).getAllByRole("link").map((l) => l.textContent)).toEqual(["Home", "Appointments", "Medicines", "Prescriptions", "Account"]);
    expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
  });

  it("R21: the switch saves Hindi on the account and every word changes", async () => {
    const api = mockApi({
      ...me(),
      "PATCH /api/v1/portal/me": () => json(200, { account: { ...PORTAL_ACCOUNT, language: "hi" } }),
      "GET /api/v1/portal/links": () => json(200, { items: [] }),
    });
    await renderPortal(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /view in Hindi/ }));

    expect(await screen.findByRole("heading", { name: "नमस्ते, Asha Patient" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "मरीज़ ऐप" })).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ language: "hi" });
    expect(api.calls.find((c) => c.method === "PATCH")?.headers.get("X-CSRF-Token")).toBe("portal-csrf");
    expect(document.cookie).toContain("me_pt_lang=hi");
    expect(screen.getByRole("navigation").closest("[lang]")).toHaveAttribute("lang", "hi");
  });

  it("R25: an ended session goes to sign-in and comes back to the same screen", async () => {
    navigation.pathname = "/portal/appointments";
    mockApi({ "GET /api/v1/portal/me": () => apiError(401, "AUTH_REFRESH_REUSED", "Ended for safety.") });
    render(
      <PortalShell>
        <MyAppointments />
      </PortalShell>,
    );
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/portal/sign-in?reason=session_ended_for_safety&next=%2Fportal%2Fappointments"),
    );
  });
});

describe("Home (FR-PRT-05, R16, R17)", () => {
  it("AC7: a new account sees no appointments and one primary action, Find a doctor", async () => {
    mockApi({ ...me(), "GET /api/v1/portal/links": () => json(200, { items: [] }) });
    await renderPortal(<Home />);
    expect(await screen.findByRole("heading", { name: "No appointments yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find a doctor" })).toHaveAttribute("href", "/portal/find");
    expect(screen.getByText("Have an invitation from your clinic?")).toBeInTheDocument();
  });

  it("R17: the next appointment, the latest prescription and what is coming up", async () => {
    mockApi({
      ...me(),
      "GET /api/v1/portal/links": () => json(200, { items: [link()] }),
      "GET /api/v1/portal/appointments": () =>
        json(200, { items: [group(CLINIC_ID, "Sample Clinic", [appointment("a1", later), appointment("a0", earlier, "COMPLETED")])] }),
      "GET /api/v1/portal/prescriptions": () => json(200, { items: [RX] }),
      "GET /api/v1/portal/reminders": () =>
        json(200, {
          items: [
            { id: "r1", clinic_id: CLINIC_ID, clinic_name: "Sample Clinic", kind: "FOLLOW_UP", follow_up_date: "2026-11-02", due_at: later.toISOString(), status: "SCHEDULED" },
          ],
        }),
    });
    await renderPortal(<Home />);
    const next = await screen.findByRole("region", { name: "Next appointment" });
    expect(next).toHaveTextContent("Sample Clinic");
    expect(next).toHaveTextContent("Confirmed");
    expect(screen.getByRole("region", { name: "Latest prescription" })).toHaveTextContent("Dr. Mehta");
    expect(screen.getByRole("region", { name: "Coming up" })).toHaveTextContent("Follow-up visit");
  });
});

describe("My appointments (FR-PRT-07, R18, R22)", () => {
  it("AC8: one group per clinic, statuses in words, times on the clinic's clock", async () => {
    const slot = new Date("2030-01-07T05:00:00Z"); // 10:30 in Asia/Kolkata
    mockApi({
      ...me(),
      "GET /api/v1/portal/appointments": () =>
        json(200, {
          items: [
            group(CLINIC_ID, "Sample Clinic", [appointment("a1", slot), appointment("a2", earlier, "NO_SHOW")]),
            group(OTHER_CLINIC_ID, "Other Clinic", [
              appointment("b1", later, "ARRIVED", { mode: "TOKENS", token_number: 4, slot_start: null }),
            ]),
          ],
        }),
      "GET /api/v1/portal/reminders": () => json(200, { items: [] }),
      "GET /api/v1/portal/booking-requests": () => json(200, { items: [] }),
    });
    await renderPortal(<MyAppointments />);
    const first = await screen.findByRole("region", { name: "Sample Clinic" });
    const other = screen.getByRole("region", { name: "Other Clinic" });
    expect(first).toHaveTextContent("10:30");
    expect(first).toHaveTextContent("Confirmed");
    expect(first).toHaveTextContent("Missed");
    expect(first).not.toHaveTextContent("Token 4");
    expect(other).toHaveTextContent("Token 4");
    expect(other).toHaveTextContent("At the clinic");
    expect(within(first).getByRole("link", { name: "Call the clinic" })).toHaveAttribute("href", "tel:+919000000010");
  });
});

describe("Prescriptions (R19, AC9)", () => {
  it("lists by clinic and marks a revision", async () => {
    mockApi({
      ...me(),
      "GET /api/v1/portal/links": () => json(200, { items: [link()] }),
      "GET /api/v1/portal/prescriptions": () => json(200, { items: [RX] }),
      "GET /api/v1/portal/bills": () => json(200, { items: [] }),
    });
    await renderPortal(<PortalPrescriptions />);
    const clinic = await screen.findByRole("region", { name: "Sample Clinic" });
    expect(within(clinic).getByRole("link", { name: "Dr. Mehta" })).toHaveAttribute("href", `/portal/prescriptions/${RX.id}`);
    expect(clinic).toHaveTextContent("Updated by the doctor");
  });

  it("opens the patient page in one main landmark and downloads the PDF through the session", async () => {
    const api = mockApi({
      ...me(),
      [`GET /api/v1/portal/prescriptions/${RX.id}`]: () => json(200, PAGE),
      [`GET /api/v1/portal/prescriptions/${RX.id}/pdf`]: () => new Response("%PDF-1", { status: 200, headers: { "Content-Type": "application/pdf" } }),
    });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    await renderPortal(<PortalPrescription rxId={RX.id} />);
    expect(await screen.findByText("Syrup X", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "हिन्दी में देखें" })).toHaveAttribute("href", `/portal/prescriptions/${RX.id}?lang=hi`);
    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled());
    expect(api.calls.some((c) => c.path.endsWith("/pdf"))).toBe(true);
  });

  it("R26: an unlinked clinic's prescription says not found", async () => {
    mockApi({ ...me(), [`GET /api/v1/portal/prescriptions/${RX.id}`]: () => apiError(404, "REQ_NOT_FOUND", "Not found.") });
    await renderPortal(<PortalPrescription rxId={RX.id} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't find this");
    expect(screen.getByRole("link", { name: "All prescriptions" })).toBeInTheDocument();
  });
});

describe("Account (R20, AC12)", () => {
  it("unlinks a clinic only after the confirmation", async () => {
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/links": () => json(200, { items: [link()] }),
      [`DELETE /api/v1/portal/links/${link().id}`]: () => json(200, { id: link().id, revoked_at: "2026-10-24T06:00:00Z" }),
    });
    await renderPortal(<PortalAccountPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Unlink Sample Clinic" }));
    expect(screen.getByText(/will disappear from your account/)).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "DELETE")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Yes, unlink" }));
    expect(await screen.findByText("Sample Clinic is no longer linked.")).toBeInTheDocument();
    expect(screen.getByText("No clinic linked yet.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "DELETE")?.headers.get("X-CSRF-Token")).toBe("portal-csrf");
  });

  it("an unverified password account is asked to confirm its email", async () => {
    mockApi({ ...me({ email_verified: false }), "GET /api/v1/portal/links": () => json(200, { items: [] }) });
    await renderPortal(<PortalAccountPage />);
    expect(await screen.findByRole("region", { name: "Confirm your email" })).toBeInTheDocument();
  });
});

describe("Find a doctor (decision 4A)", () => {
  it("M6c-P7 (discovery R14): opens the directory search and still says how to link", async () => {
    mockApi(me());
    await renderPortal(<FindADoctor />);
    expect(screen.getByRole("link", { name: "Search doctors and clinics" })).toHaveAttribute("href", "/find");
    expect(screen.getByText(/ask your clinic for an invitation/)).toBeInTheDocument();
  });
});
