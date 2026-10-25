import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { navigation, resetNavigation } from "@/test/navigation";

import { MyAppointments } from "./MyAppointments";
import { RequestBooking } from "./RequestBooking";
import { me, renderPortal } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const DOCTOR = "0192f0a0-0000-7000-8000-0000000000d1";
const SESSION = "2026-11-02T04:30:00Z";
const SLOT = "2026-11-02T05:30:00Z";

const CLINIC = {
  name: "Sample Clinic",
  slug: "sample-clinic",
  address_line: "12 MG Road",
  city: "Pune",
  state: "MH",
  pincode: "411001",
  phone_e164: "+919000000010",
  timezone: "Asia/Kolkata",
  booking_mode: "SLOTS",
  map_url: null,
  requires_age_sex: false,
  doctors: [{ id: DOCTOR, display_name: "Dr. Mehta", qualification: null, specialty: null, hours: [] }],
};

const REQUESTED = {
  id: "0192f0a0-0000-7000-8000-0000000000a1",
  status: "REQUESTED",
  clinic_id: "0192f0a0-0000-7000-8000-0000000000e2",
  clinic_name: "Sample Clinic",
  clinic_slug: "sample-clinic",
  clinic_phone_e164: "+919000000010",
  timezone: "Asia/Kolkata",
  doctor_name: "Dr. Mehta",
  mode: "SLOTS",
  starts_at: SLOT,
  created_at: "2026-10-30T05:30:00Z",
};

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_pt_csrf=csrf-token; path=/";
  navigation.pathname = "/portal/request";
  navigation.search = `?clinic=sample-clinic&doctor=${DOCTOR}&session=${SESSION}&slot=${SLOT}`;
});

afterEach(() => {
  document.cookie = "me_pt_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("the request form (M6b-P4, FR-PUB-02, FR-BKG-01)", () => {
  it("R9, R12: asks for the phone only, sends the chosen slot, and says Requested", async () => {
    const api = mockApi({
      ...me(),
      "GET /api/v1/public/clinics/sample-clinic": () => json(200, CLINIC),
      "POST /api/v1/portal/booking-requests": () => json(201, REQUESTED),
    });
    await renderPortal(<RequestBooking />);
    const form = await screen.findByRole("region", { name: "Ask for this time" });
    expect(within(form).getByText(/Dr\. Mehta at Sample Clinic/)).toBeInTheDocument();
    expect(within(form).getByLabelText(/^Age in years \(optional\)/)).not.toBeRequired();

    const send = within(form).getByRole("button", { name: "Send request" });
    expect(send).toBeDisabled(); // no phone, no confirmation yet
    fireEvent.change(within(form).getByLabelText(/Phone number/), { target: { value: "9000000601" } });
    fireEvent.click(within(form).getByLabelText("This is not an emergency."));
    expect(send).toBeEnabled();
    fireEvent.click(send);

    expect(await screen.findByText("Requested")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
      clinic_slug: "sample-clinic",
      doctor_id: DOCTOR,
      session_start: SESSION,
      slot_start: SLOT,
      contact_phone: "9000000601",
      not_emergency_ack: true,
    });
  });

  it("R12: age and sex are required when the clinic says so", async () => {
    mockApi({ ...me(), "GET /api/v1/public/clinics/sample-clinic": () => json(200, { ...CLINIC, requires_age_sex: true }) });
    await renderPortal(<RequestBooking />);
    const form = await screen.findByRole("region", { name: "Ask for this time" });
    expect(within(form).getByLabelText(/^Age in years/)).toBeRequired();
    expect(within(form).getByLabelText(/^Sex/)).toBeRequired();
  });

  it("R4: a time that was just taken says so and offers the page again", async () => {
    mockApi({
      ...me(),
      "GET /api/v1/public/clinics/sample-clinic": () => json(200, CLINIC),
      "POST /api/v1/portal/booking-requests": () => apiError(409, "APT_SLOT_HELD", "Held."),
    });
    await renderPortal(<RequestBooking />);
    const form = await screen.findByRole("region", { name: "Ask for this time" });
    fireEvent.change(within(form).getByLabelText(/Phone number/), { target: { value: "9000000601" } });
    fireEvent.click(within(form).getByLabelText("This is not an emergency."));
    fireEvent.click(within(form).getByRole("button", { name: "Send request" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent(/clinic is holding it/);
    expect(within(form).getByRole("link", { name: "Choose another time" })).toHaveAttribute("href", "/c/sample-clinic");
  });

  it("R15: a rate limit says how long to wait", async () => {
    mockApi({
      ...me(),
      "GET /api/v1/public/clinics/sample-clinic": () => json(200, CLINIC),
      "POST /api/v1/portal/booking-requests": () => apiError(429, "PRT_RATE_LIMITED", "Slow down.", { "Retry-After": "90" }),
    });
    await renderPortal(<RequestBooking />);
    const form = await screen.findByRole("region", { name: "Ask for this time" });
    fireEvent.change(within(form).getByLabelText(/Phone number/), { target: { value: "9000000601" } });
    fireEvent.click(within(form).getByLabelText("This is not an emergency."));
    fireEvent.click(within(form).getByRole("button", { name: "Send request" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("90 seconds");
  });

  it("R6: an unverified account is sent to confirm its email first", async () => {
    mockApi({ ...me({ email_verified: false }), "GET /api/v1/public/clinics/sample-clinic": () => json(200, CLINIC) });
    await renderPortal(<RequestBooking />);
    const form = await screen.findByRole("region", { name: "Ask for this time" });
    expect(within(form).getByRole("link", { name: "Go to my account" })).toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Send request" })).toBeDisabled();
  });

  it("R2: an unknown clinic is the plain 'not available'", async () => {
    mockApi({ ...me(), "GET /api/v1/public/clinics/sample-clinic": () => apiError(404, "REQ_NOT_FOUND", "Not found.") });
    await renderPortal(<RequestBooking />);
    expect(await screen.findByText("This time is not available any more.")).toBeInTheDocument();
  });
});

describe("My appointments shows requests (R23)", () => {
  it("lists a request as Requested, also with no linked clinic", async () => {
    mockApi({
      ...me(),
      "GET /api/v1/portal/appointments": () => json(200, { items: [] }),
      "GET /api/v1/portal/reminders": () => json(200, { items: [] }),
      "GET /api/v1/portal/booking-requests": () => json(200, { items: [REQUESTED] }),
    });
    await renderPortal(<MyAppointments />);
    const card = await screen.findByRole("region", { name: "Requested" });
    expect(within(card).getByText(/Dr\. Mehta · Sample Clinic/)).toBeInTheDocument();
    expect(within(card).getAllByText("Requested").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.queryByText(/no appointments/i)).not.toBeInTheDocument());
  });
});

describe("answering a proposal (M6b-P5, R42, R43, R49)", () => {
  const PROPOSED = {
    ...REQUESTED,
    status: "PROPOSED",
    starts_at: "2026-11-03T05:30:00Z",
    original_starts_at: SLOT,
    decline_reason: null,
    respond_by: "2026-11-02T08:30:00Z",
  };

  function routes(extra: Record<string, () => Response>) {
    return {
      ...me(),
      "GET /api/v1/portal/appointments": () => json(200, { items: [] }),
      "GET /api/v1/portal/reminders": () => json(200, { items: [] }),
      ...extra,
    };
  }

  it("shows the suggested time and books it with one tap", async () => {
    const api = mockApi(
      routes({
        "GET /api/v1/portal/booking-requests": () => json(200, { items: [PROPOSED] }),
        [`POST /api/v1/portal/booking-requests/${PROPOSED.id}/accept-proposal`]: () => json(200, { id: PROPOSED.id, status: "ACCEPTED" }),
      }),
    );
    await renderPortal(<MyAppointments />);
    const card = await screen.findByRole("region", { name: "Requested" });
    expect(within(card).getByText("Suggested another time")).toBeInTheDocument();
    expect(within(card).getByText(/The clinic suggests .* instead of /)).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Accept this time" }));
    await waitFor(() => expect(api.calls.some((c) => c.path.endsWith("/accept-proposal"))).toBe(true));
    expect(api.calls.filter((c) => c.method === "POST").map((c) => c.path)).toEqual([
      `/api/v1/portal/booking-requests/${PROPOSED.id}/accept-proposal`,
    ]);
  });

  it("No thanks declines it", async () => {
    const api = mockApi(
      routes({
        "GET /api/v1/portal/booking-requests": () => json(200, { items: [PROPOSED] }),
        [`POST /api/v1/portal/booking-requests/${PROPOSED.id}/decline-proposal`]: () => json(200, { id: PROPOSED.id, status: "DECLINED" }),
      }),
    );
    await renderPortal(<MyAppointments />);
    fireEvent.click(await screen.findByRole("button", { name: "No thanks" }));
    await waitFor(() => expect(api.calls.some((c) => c.path.endsWith("/decline-proposal"))).toBe(true));
  });

  it("a declined request says why, an expired one says to call, both with the call button", async () => {
    mockApi(
      routes({
        "GET /api/v1/portal/booking-requests": () =>
          json(200, {
            items: [
              { ...REQUESTED, id: "d1", status: "DECLINED", decline_reason: "DOCTOR_UNAVAILABLE", original_starts_at: null, respond_by: null },
              { ...REQUESTED, id: "e1", status: "EXPIRED", decline_reason: null, original_starts_at: null, respond_by: null },
            ],
          }),
      }),
    );
    await renderPortal(<MyAppointments />);
    const card = await screen.findByRole("region", { name: "Requested" });
    expect(within(card).getByText("The doctor is not available then.")).toBeInTheDocument();
    expect(within(card).getByText(/did not reply in time/)).toBeInTheDocument();
    expect(within(card).getAllByRole("link", { name: "Call the clinic" })).toHaveLength(2);
  });
});