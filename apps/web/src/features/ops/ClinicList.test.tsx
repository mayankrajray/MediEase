import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { CLINIC_A, CLINIC_B, ops } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { replace, resetNavigation } from "@/test/navigation";

import { ClinicList } from "./ClinicList";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const checklist = (overrides: Record<string, unknown> = {}) => ({
  started_at: "2026-10-03T08:00:00+00:00",
  clinic_created_at: "2026-10-03T08:00:00+00:00",
  doctors_added_at: "2026-10-03T08:10:00+00:00",
  staff_invited_at: "2026-10-03T08:25:00+00:00",
  patients_imported_at: null,
  first_appointment_at: null,
  first_prescription_at: null,
  ...overrides,
});

const row = (overrides: Record<string, unknown> = {}) => ({
  id: CLINIC_A,
  name: "Alpha Clinic",
  slug: "alpha-clinic",
  timezone: "Asia/Kolkata",
  status: "ONBOARDING",
  phone_e164: null,
  address_line: null,
  city: null,
  state: null,
  pincode: null,
  specialties: [],
  onboarding: checklist(),
  // M6d-P7: the plan and trial on each row.
  subscription: { plan: "CLINIC", plan_name: "Clinic", trial_state: "ACTIVE", trial_ends_at: "2026-10-17T08:00:00+00:00", trial_days_left: 9 },
  ...overrides,
});

const base = { "GET /api/v1/me": () => json(200, ops()) };

function renderList() {
  return render(
    <SessionProvider>
      <ClinicList />
    </SessionProvider>,
  );
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("ClinicList", () => {
  it("FR-OPS-04: shows each clinic's state, start in its own zone, steps and time to invitation", async () => {
    mockApi({
      ...base,
      "GET /api/v1/ops/clinics": () =>
        json(200, {
          items: [
            row(),
            row({
              id: CLINIC_B,
              name: "Beta Clinic",
              slug: "beta-clinic",
              status: "ACTIVE",
              timezone: "Asia/Dubai",
              onboarding: checklist({ doctors_added_at: null, staff_invited_at: null }),
            }),
          ],
        }),
    });

    renderList();

    expect(await screen.findByRole("heading", { name: "Clinics" })).toBeInTheDocument();
    const alpha = (await screen.findByRole("row", { name: /Alpha Clinic/ })) as HTMLElement;
    expect(within(alpha).getByText("Setting up")).toBeInTheDocument();
    expect(within(alpha).getByText(/3 Oct 2026, 13:30.*IST/)).toBeInTheDocument(); // 08:00 UTC
    expect(alpha).toHaveTextContent("Clinic created: yes");
    expect(alpha).toHaveTextContent("Doctors added: yes");
    expect(alpha).toHaveTextContent("Staff invited: yes");
    expect(within(alpha).getByText("25 min")).toBeInTheDocument();
    const beta = screen.getByRole("row", { name: /Beta Clinic/ });
    expect(within(beta).getByText("Active")).toBeInTheDocument();
    expect(within(beta).getByText(/12:00/)).toBeInTheDocument(); // 08:00 UTC is 12:00 in Dubai
    expect(beta).toHaveTextContent("Doctors added: no");
    expect(beta).toHaveTextContent("Staff invited: no");
  });

  it("offers Continue setup only for a clinic that is still being set up", async () => {
    mockApi({
      ...base,
      "GET /api/v1/ops/clinics": () => json(200, { items: [row(), row({ id: CLINIC_B, name: "Beta Clinic", status: "ACTIVE" })] }),
    });

    renderList();

    const link = await screen.findByRole("link", { name: "Continue setup for Alpha Clinic" });
    expect(link).toHaveAttribute("href", `/ops/clinics/new?clinic=${CLINIC_A}`);
    expect(screen.getAllByRole("link", { name: /Continue setup/ })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Create clinic" })).toHaveAttribute("href", "/ops/clinics/new");
  });

  it("says so when there are no clinics yet", async () => {
    mockApi({ ...base, "GET /api/v1/ops/clinics": () => json(200, { items: [] }) });

    renderList();

    expect(await screen.findByText(/No clinics yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create clinic" })).toBeInTheDocument();
  });

  it("shows dashes for a clinic with no checklist", async () => {
    mockApi({
      ...base,
      "GET /api/v1/ops/clinics": () => json(200, { items: [row({ status: "ACTIVE", onboarding: null })] }),
    });

    renderList();

    const alpha = await screen.findByRole("row", { name: /Alpha Clinic/ });
    expect(within(alpha).getAllByText("–")).toHaveLength(3);
  });

  it("an unreachable API shows the message with Try again, which reloads", async () => {
    let up = false;
    mockApi({
      ...base,
      "GET /api/v1/ops/clinics": () => {
        if (!up) throw new TypeError("fetch failed");
        return json(200, { items: [row()] });
      },
    });
    renderList();
    expect(await screen.findByRole("alert")).toHaveTextContent("The API could not be reached.");

    up = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("row", { name: /Alpha Clinic/ })).toBeInTheDocument();
  });

  it("R7: a session that has ended sends the person to sign in", async () => {
    window.history.replaceState(null, "", "/ops");
    mockApi({
      ...base,
      "GET /api/v1/ops/clinics": () => apiError(403, "AUTH_ACCOUNT_DISABLED", "Account disabled"),
    });

    renderList();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fops&reason=account_disabled"));
  });
});

describe("ClinicList plans (M6d-P7, FR-SUB-01)", () => {
  it("R7, R8: shows each clinic's plan and an ended trial, and saves a new plan", async () => {
    let plan = "SOLO";
    const api = mockApi({
      ...base,
      "GET /api/v1/ops/clinics": () =>
        json(200, {
          items: [
            row({
              status: "ACTIVE",
              subscription: { plan, plan_name: "Solo", trial_state: "ENDED", trial_ends_at: "2026-10-17T08:00:00+00:00", trial_days_left: 0 },
            }),
          ],
        }),
      [`PUT /api/v1/ops/clinics/${CLINIC_A}/plan`]: [
        () => apiError(409, "SUB_PLAN_TOO_SMALL", "The clinic has 2 doctors; the Solo plan allows 1."),
        () => {
          plan = "PLUS";
          return json(200, {});
        },
      ],
    });
    renderList();

    const cell = await screen.findByText("Free trial ended");
    expect(cell).toBeInTheDocument();
    const picker = screen.getByLabelText("Plan for Alpha Clinic");
    expect(picker).toHaveValue("SOLO");
    expect(screen.getByRole("button", { name: "Save plan for Alpha Clinic" })).toBeDisabled();

    fireEvent.change(picker, { target: { value: "CLINIC" } });
    fireEvent.click(screen.getByRole("button", { name: "Save plan for Alpha Clinic" }));
    expect(await screen.findByText(/the Solo plan allows 1/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Plan for Alpha Clinic"), { target: { value: "PLUS" } });
    fireEvent.click(screen.getByRole("button", { name: "Save plan for Alpha Clinic" }));
    expect(await screen.findByText("Alpha Clinic is now on the Clinic Plus plan.")).toBeInTheDocument();
    expect(api.calls.filter((c) => c.method === "PUT").map((c) => c.body)).toEqual([{ plan: "CLINIC" }, { plan: "PLUS" }]);
  });
});
