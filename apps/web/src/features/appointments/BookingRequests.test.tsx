import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { patient, renderInWorkspace } from "@/features/patients/testing";
import { boardRoutes, doctor, session } from "@/features/queue/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { BookDrawer, heldUntil } from "./BookDrawer";
import { BookingRequests } from "./BookingRequests";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

const iso = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();

const REQUEST = {
  id: "0192f0a0-0000-7000-8000-0000000000a1",
  full_name: "Requester One",
  age_years: 34,
  sex: "FEMALE",
  phone_e164: "+919000000601",
  reason: "cough",
  doctor_name: "Dr Meera Iyer",
  mode: "SLOTS",
  starts_at: iso(60 * 24),
  created_at: iso(-10),
  hold_expires_at: iso(110),
  holding: true,
  hold_overridden: false,
  respond_by: iso(230),
};

describe("booking requests (M6b-P4, spec R22)", () => {
  it("lists what patients asked for, with the hold and the reply-by time", async () => {
    mockApi({
      ...boardRoutes,
      "GET /api/v1/booking-requests": () => json(200, { items: [REQUEST, { ...REQUEST, id: "b2", full_name: "Second Person", holding: false, hold_overridden: true, age_years: null, sex: null, reason: null }] }),
    });
    renderInWorkspace(<BookingRequests />);
    const table = await screen.findByRole("table", {}, { timeout: 5000 });
    expect(within(table).getByText("Requester One")).toBeInTheDocument();
    expect(within(table).getByText("34 years, Female")).toBeInTheDocument();
    expect(within(table).getByText(/Held until/)).toBeInTheDocument();
    expect(within(table).getByText("Booked over")).toBeInTheDocument();
    expect(within(table).getAllByRole("link", { name: "+919000000601" })[0]).toHaveAttribute("href", "tel:+919000000601");
  });

  it("says plainly when there are none", async () => {
    mockApi({ ...boardRoutes, "GET /api/v1/booking-requests": () => json(200, { items: [] }) });
    renderInWorkspace(<BookingRequests />);
    expect(await screen.findByText("No open requests", {}, { timeout: 5000 })).toBeInTheDocument();
  });
});

describe("booking over a held time (R18, R18a)", () => {
  const held = (slot: string | null, minutes = 90) => ({ slot_start: slot, until: iso(minutes) });

  it("heldUntil: a held slot, a token session whose every free place is held, and neither", () => {
    const now = Date.now();
    const slotted = session({ mode: "SLOTS", slots: [{ starts_at: iso(10), ends_at: iso(25), available: true }], held: [held(iso(10))] });
    expect(heldUntil(slotted, { sessionId: slotted.id, slotStart: slotted.slots[0]?.starts_at ?? "" }, now)).toBeDefined();
    const tokens = session({ available: 1, held: [held(null)] });
    expect(heldUntil(tokens, { sessionId: tokens.id }, now)).toBeDefined();
    expect(heldUntil(session({ available: 2, held: [held(null)] }), { sessionId: "x" }, now)).toBeUndefined();
    expect(heldUntil(session({ available: 1, held: [{ slot_start: null, until: iso(-5) }] }), { sessionId: "x" }, now)).toBeUndefined();
  });

  function open() {
    renderInWorkspace(
      <BookDrawer
        target={{ kind: "book", patient: patient() }}
        doctors={[doctor()]}
        doctorId={doctor().id}
        date={session().on_date}
        onDone={vi.fn()}
        onClose={vi.fn()}
      />,
    );
  }

  it("asks before booking over a hold, sends nothing, and then sends override_hold", async () => {
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/sessions": () => json(200, { items: [session({ available: 1, held: [held(null)] })] }),
      "POST /api/v1/appointments": () => json(201, { ...session(), token_number: 2, slot_start: null, on_date: session().on_date }),
    });
    open();
    const dialog = await screen.findByRole("dialog", { name: "Book appointment" }, { timeout: 5000 });
    await within(dialog).findByText(/1 held for online requests/);
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm booking" }));

    const ask = await within(dialog).findByRole("alertdialog");
    expect(ask).toHaveTextContent("A patient asked for this time online");
    expect(api.calls.some((c) => c.method === "POST")).toBe(false);

    fireEvent.click(within(ask).getByRole("button", { name: /Book anyway/ }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "POST")).toBe(true));
    expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({ override_hold: true });
  });

  it("choosing another time backs out without sending anything", async () => {
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/sessions": () => json(200, { items: [session({ available: 1, held: [held(null)] })] }),
    });
    open();
    const dialog = await screen.findByRole("dialog", { name: "Book appointment" }, { timeout: 5000 });
    await within(dialog).findByText(/held for online requests/);
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm booking" }));
    fireEvent.click(await within(dialog).findByRole("button", { name: "Choose another time" }));
    expect(within(dialog).queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("a hold that appeared meanwhile (409 APT_SLOT_HELD) asks the same question", async () => {
    mockApi({
      ...boardRoutes,
      "GET /api/v1/sessions": () => json(200, { items: [session()] }),
      "POST /api/v1/appointments": () => apiError(409, "APT_SLOT_HELD", "Held.", {}, { held_until: iso(60) }),
    });
    open();
    const dialog = await screen.findByRole("dialog", { name: "Book appointment" }, { timeout: 5000 });
    await within(dialog).findByRole("radio");
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm booking" }));
    expect(await within(dialog).findByRole("alertdialog")).toHaveTextContent(/Book anyway only if you have agreed/);
  });
});
