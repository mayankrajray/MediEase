import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { TodayDashboard } from "@/features/dashboard/TodayDashboard";
import { todayOf } from "@/features/dashboard/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { appointment, doctor } from "@/features/queue/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import type { BookingToMove } from "./api";
import { BookingsToMove } from "./BookingsToMove";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const desk = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "APPOINTMENTS_MANAGE", "QUEUE_MOVE"],
});
const A1 = "0192f0a0-0000-7000-8000-00000000c001";

function item(overrides: Partial<BookingToMove> = {}): BookingToMove {
  return {
    id: A1,
    status: "BOOKED",
    doctor_id: doctor().id,
    session_id: "0192f0a0-0000-7000-8000-00000000c101",
    on_date: "2026-11-03",
    starts_at: "2026-11-03T04:30:00+00:00",
    slot_start: null,
    token_number: 4,
    reason: "LEAVE",
    patient: { id: "0192f0a0-0000-7000-8000-00000000c201", code: "SC-0004", first_name: "Asha", phone_masked: "+91******0101" },
    ...overrides,
  };
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

function render(items: readonly BookingToMove[], extra: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({
    ...workspaceRoutes,
    "GET /api/v1/me": () => json(200, person([desk])),
    "GET /api/v1/clinic/doctors": () => json(200, { items: [doctor()] }),
    "GET /api/v1/appointments/to-move": () => json(200, { items }),
    ...extra,
  });
  renderInWorkspace(<BookingsToMove />);
  return api;
}

describe("bookings to move (M6a-P8, FR-APT-09, decision 6A)", () => {
  it("lists who and where, and why, without the full name", async () => {
    render([item(), item({ id: "0192f0a0-0000-7000-8000-00000000c002", reason: "SCHEDULE_CHANGED", token_number: 5 })]);

    const table = await screen.findByRole("table", { name: "Bookings to move, earliest first" }, { timeout: 5000 });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Asha · SC-0004");
    expect(rows[0]).toHaveTextContent("+91******0101");
    expect(rows[0]).toHaveTextContent("token 4");
    expect(rows[0]).toHaveTextContent("Doctor on leave");
    expect(rows[1]).toHaveTextContent("Schedule changed");
    expect(rows[0]).toHaveTextContent(doctor().display_name);
  });

  it("cancels with Doctor unavailable preselected, then refreshes the list", async () => {
    const api = render([item()], {
      [`POST /api/v1/appointments/${A1}/cancel`]: () => json(200, appointment({ id: A1, status: "CANCELLED" })),
    });
    const button = await screen.findByRole("button", { name: "Cancel Asha · SC-0004" }, { timeout: 5000 });
    fireEvent.click(button);

    const dialog = await screen.findByRole("dialog", { name: /Cancel Asha · SC-0004's appointment/ });
    expect(within(dialog).getByRole("radio", { name: "Doctor unavailable" })).toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel appointment" }));

    expect(await screen.findByText(/Asha · SC-0004's appointment cancelled/)).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ reason: "DOCTOR_UNAVAILABLE" });
    await waitFor(() => expect(api.count("GET /api/v1/appointments/to-move")).toBe(2));
  }, 15_000);

  it("says when there is nothing to move, and offers a retry after a failure", async () => {
    render([], {
      "GET /api/v1/appointments/to-move": [
        () => apiError(503, "SYS_UNAVAILABLE", "Try again shortly."),
        () => json(200, { items: [] }),
      ],
    });
    fireEvent.click(await screen.findByRole("button", { name: /Try again/ }, { timeout: 5000 }));
    expect(await screen.findByText("Nothing to move")).toBeInTheDocument();
  });
});

describe("Today's bookings-to-move tile (decision 6A)", () => {
  it("links to the list when there are some, and is absent when there are none", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, person([desk])),
      "GET /api/v1/dashboard/today": () => json(200, todayOf({ bookings_to_move: 3 })),
    });
    renderInWorkspace(<TodayDashboard />);
    expect(await screen.findByRole("link", { name: /Bookings to move\s*3/ }, { timeout: 5000 })).toHaveAttribute(
      "href",
      "/bookings-to-move",
    );
  });

  it("is absent with nothing to move", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, person([desk])),
      "GET /api/v1/dashboard/today": () => json(200, todayOf({ bookings_to_move: 0 })),
    });
    renderInWorkspace(<TodayDashboard />);
    await screen.findByRole("link", { name: /Follow-ups due/ }, { timeout: 5000 });
    expect(screen.queryByRole("link", { name: /Bookings to move/ })).not.toBeInTheDocument();
  });
});
