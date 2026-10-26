import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { DirectoryListing } from "./DirectoryListing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const DOCTOR = "0192f0a0-0000-7000-8000-0000000000d1";

const listing = (overrides: Record<string, unknown> = {}, doctor: Record<string, unknown> = {}) => ({
  listed: false,
  listed_at: null,
  verified: true,
  discoverable: false,
  search_indexing: true,
  language_options: ["English", "Hindi"],
  problems: ["NO_BOOKABLE_DOCTOR"],
  doctors: [
    {
      id: DOCTOR,
      display_name: "Dr. Sample Doctor",
      is_active: true,
      verified: true,
      visible: false,
      has_schedule: true,
      can_be_visible: true,
      languages: [],
      fee_paise: null,
      show_fee: false,
      problems: ["HIDDEN"],
      ...doctor,
    },
  ],
  ...overrides,
});

const owner = () => person([membership(CLINIC_A, "Alpha Clinic", "OWNER", { permissions: ["CLINIC_VIEW", "CLINIC_MANAGE", "DOCTORS_VIEW"] })]);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => vi.unstubAllGlobals());

describe("the directory listing (M6c-P4, clinic-onboarding R50-R55)", () => {
  it("says what stands in the way, then shows the doctor and lists the clinic", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/listing": () => json(200, listing()),
      [`PUT /api/v1/clinic/listing/doctors/${DOCTOR}`]: () => json(200, listing({ problems: [] }, { visible: true, problems: [] })),
      "PUT /api/v1/clinic/listing": () =>
        json(200, listing({ problems: [], listed: true, listed_at: "2026-10-26T06:00:00+00:00", discoverable: true }, { visible: true, problems: [] })),
    });
    renderInWorkspace(<DirectoryListing />);
    const listed = await screen.findByLabelText("Listed in the MediEase directory");
    expect(listed).toBeDisabled();
    expect(screen.getByText("Show at least one verified doctor who has weekly hours.")).toBeInTheDocument();
    expect(screen.getByText("Hidden")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Show Dr. Sample Doctor on the public page and in search"));
    expect(await screen.findByText("Dr. Sample Doctor is shown.")).toBeInTheDocument();
    expect(listed).toBeEnabled();
    fireEvent.click(listed);
    expect(await screen.findByText("Listed. Patients can find the clinic.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT" && c.path === "/api/v1/clinic/listing")?.body).toEqual({ listed: true });
  });

  it("an unverified doctor cannot be shown", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/listing": () => json(200, listing({}, { verified: false, can_be_visible: false, problems: ["NOT_VERIFIED", "HIDDEN"] })),
    });
    renderInWorkspace(<DirectoryListing />);
    expect(await screen.findByLabelText("Show Dr. Sample Doctor on the public page and in search")).toBeDisabled();
    expect(screen.getByText("Not verified by MediEase · Hidden")).toBeInTheDocument();
  });

  it("shows the API's refusal", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/listing": () => json(200, listing({ listed: true, problems: [] })),
      "PUT /api/v1/clinic/listing": () => apiError(409, "CLN_LISTING_BLOCKED", "The clinic cannot be listed yet."),
    });
    renderInWorkspace(<DirectoryListing />);
    fireEvent.click(await screen.findByLabelText("Listed in the MediEase directory"));
    expect(await screen.findByText(/The clinic cannot be listed yet/)).toBeInTheDocument();
  });

  it("M6d-P1 (D8): shows the consultation price from Fees and sends only whether to show it", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/listing": () => json(200, listing({}, { fee_paise: 50000 })),
      [`PUT /api/v1/clinic/listing/doctors/${DOCTOR}/profile`]: () => json(200, listing({}, { fee_paise: 50000, show_fee: true, languages: ["Hindi"] })),
    });
    renderInWorkspace(<DirectoryListing />);
    const show = await screen.findByLabelText("Show the consultation fee publicly");
    expect(screen.getByText("Their consultation price is ₹500.00. Change it on Fees.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Set prices on Fees" })).toHaveAttribute("href", "/settings/fees");
    fireEvent.click(screen.getByLabelText("Hindi"));
    fireEvent.click(show);
    fireEvent.click(screen.getByRole("button", { name: /Save profile/ }));
    expect(await screen.findByText("Dr. Sample Doctor's profile saved.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT" && c.path.endsWith("/profile"))?.body).toEqual({ languages: ["Hindi"], show_fee: true });
  });
});
