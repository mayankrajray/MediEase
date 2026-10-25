import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { ops } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { ReviewApplication } from "./ReviewApplication";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const ID = "0192f0a0-0000-7000-8000-0000000000c1";
const DOCTOR = "0192f0a0-0000-7000-8000-0000000000d1";
const BASE = `/api/v1/ops/applications/${ID}`;

type Check = {
  register_checked: boolean;
  certificate_matches: boolean;
  result: "VERIFIED" | "NOT_VERIFIED";
  note: null;
  checked_at: string;
  checked_by: string;
};

const verified: Check = {
  register_checked: true,
  certificate_matches: true,
  result: "VERIFIED",
  note: null,
  checked_at: "2026-10-26T06:00:00+00:00",
  checked_by: "0192f0a0-0000-7000-8000-0000000000e1",
};

const detail = (overrides: Record<string, unknown> = {}, check: Check | null = null) => ({
  id: ID,
  reference: "MA-2026-0042",
  kind: "SOLO_DOCTOR",
  status: "PENDING",
  clinic_name: "Sample Applying Clinic",
  address_line: "1 Sample Road",
  city: "Pune",
  state: "Maharashtra",
  pincode: "411001",
  clinic_phone_e164: "+919800000001",
  specialties: ["General Medicine"],
  owner_name: "Dr. Sample Owner",
  owner_phone_e164: "+919800000002",
  owner_email: "owner@example.test",
  owner_practises: true,
  submitted_at: "2026-10-26T05:00:00+00:00",
  email_verified_at: "2026-10-26T05:10:00+00:00",
  taken_by: null,
  taken_at: null,
  decided_at: null,
  decision_reason: null,
  decision_message: null,
  duplicate_of: [],
  clinic_id: null,
  all_verified: check?.result === "VERIFIED",
  doctors: [
    {
      id: DOCTOR,
      position: 1,
      name: "Dr. Sample Owner",
      qualification: "MBBS",
      council: "Sample State Medical Council",
      registration_number: "SMC-1",
      is_owner: true,
      certificate: { content_type: "application/pdf", size: 1000 },
      check,
    },
  ],
  ...overrides,
});

function renderIt() {
  return render(
    <SessionProvider>
      <ReviewApplication applicationId={ID} />
    </SessionProvider>,
  );
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => vi.unstubAllGlobals());

describe("reviewing an application (M6c-P2, P3; clinic-onboarding R26-R44)", () => {
  it("takes, verifies the doctor and approves with the reviewer's choices", async () => {
    const { calls } = mockApi({
      "GET /api/v1/me": () => json(200, ops()),
      [`GET ${BASE}`]: () => json(200, detail()),
      [`POST ${BASE}/take`]: () => json(200, detail({ status: "UNDER_REVIEW" })),
      [`PUT ${BASE}/doctors/${DOCTOR}/check`]: () => json(200, detail({ status: "UNDER_REVIEW" }, verified)),
      [`POST ${BASE}/approve`]: () =>
        json(201, {
          application: detail({ status: "APPROVED", clinic_id: "0192f0a0-0000-7000-8000-0000000000f1" }, verified),
          clinic: { id: "0192f0a0-0000-7000-8000-0000000000f1", name: "Sample Applying Clinic" },
          invitation_delivery: "email",
        }),
    });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Take for review" }));
    expect(await screen.findByRole("button", { name: "Approve and create the clinic" })).toBeDisabled();

    const verify = screen.getByRole("button", { name: "Mark verified" });
    expect(verify).toBeDisabled(); // R30: both checks first
    fireEvent.click(screen.getByLabelText("Found on the council's register"));
    fireEvent.click(screen.getByLabelText("The certificate matches the application"));
    fireEvent.click(verify);
    expect(await screen.findByText("Doctor 1 checked.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve and create the clinic" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText(/Clinic URL name/)).toHaveValue("sample-applying-clinic");
    fireEvent.change(within(dialog).getByLabelText("City"), { target: { value: "Mumbai" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve and email the owner" }));

    expect(await screen.findByText(/Approved\. Sample Applying Clinic is created/)).toBeInTheDocument();
    const approve = calls.find((c) => c.path === `${BASE}/approve`);
    expect(approve?.body).toEqual({
      slug: "sample-applying-clinic",
      booking_mode: "TOKENS",
      timezone: "Asia/Kolkata",
      clinic_name: null,
      address_line: null,
      city: "Mumbai",
      state: null,
      pincode: null,
    });
  });

  it("shows a taken slug against its field and keeps the dialog open", async () => {
    mockApi({
      "GET /api/v1/me": () => json(200, ops()),
      [`GET ${BASE}`]: () => json(200, detail({ status: "UNDER_REVIEW" }, verified)),
      [`POST ${BASE}/approve`]: () => apiError(409, "CLN_SLUG_TAKEN", "That URL name is already used."),
    });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Approve and create the clinic" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve and email the owner" }));
    expect(await within(dialog).findByText("That URL name is already used.")).toBeInTheDocument();
  });

  it("rejecting with Other needs a message", async () => {
    mockApi({
      "GET /api/v1/me": () => json(200, ops()),
      [`GET ${BASE}`]: () => json(200, detail({ status: "UNDER_REVIEW" })),
    });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Reject…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Reason the applicant will read/), { target: { value: "OTHER" } });
    expect(within(dialog).getByRole("button", { name: "Reject and email the applicant" })).toBeDisabled();
    expect(within(dialog).getByText("Write a message for Other.")).toBeInTheDocument();
  });
});
