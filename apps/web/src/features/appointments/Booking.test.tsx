import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PATIENT_ID, patient, renderInWorkspace } from "@/features/patients/testing";
import { boardRoutes, doctor, session } from "@/features/queue/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { BookDrawer, preselect } from "./BookDrawer";
import { PatientAppointments } from "./PatientAppointments";

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

function slotSession() {
  return session({
    mode: "SLOTS",
    slot_minutes: 15,
    starts_at: iso(-20),
    ends_at: iso(40),
    capacity: 4,
    booked_count: 1,
    available: 3,
    next_token: null,
    slots: [
      { starts_at: iso(-20), ends_at: iso(-5), available: true }, // over: never offered
      { starts_at: iso(-5), ends_at: iso(10), available: false }, // taken
      { starts_at: iso(10), ends_at: iso(25), available: true },
      { starts_at: iso(25), ends_at: iso(40), available: true },
    ],
  });
}

describe("preselect (AC6)", () => {
  it("offers the next token, or the earliest free slot that has not ended", () => {
    const now = Date.now();
    expect(preselect([session()], now)).toEqual({ sessionId: session().id });
    const slots = slotSession();
    expect(preselect([slots], now)?.slotStart).toBe(slots.slots[2]?.starts_at);
    expect(preselect([session({ status: "CLOSED" }), session({ available: 0 })], now)).toBeUndefined();
  });
});

describe("booking drawer (M3-P5, FR-APT-03)", () => {
  function open(onDone = vi.fn()) {
    renderInWorkspace(
      <BookDrawer target={{ kind: "book" }} doctors={[doctor()]} doctorId={doctor().id} date={session().on_date} onDone={onDone} onClose={vi.fn()} />,
    );
    return onDone;
  }

  it("AC6: pick the patient, the next token is chosen, Confirm — two interactions in the drawer", async () => {
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/sessions": () => json(200, { items: [session()] }),
      "GET /api/v1/patients": () => json(200, { items: [patient()] }),
      "POST /api/v1/appointments": () => json(201, { ...session(), token_number: 2, slot_start: null, on_date: session().on_date }),
    });
    const onDone = open();
    const dialog = await screen.findByRole("dialog", { name: "Book appointment" }, { timeout: 5000 });

    expect(within(dialog).getByLabelText("Patient")).toHaveFocus();
    fireEvent.change(within(dialog).getByLabelText("Patient"), { target: { value: "bina" } });
    fireEvent.click(await within(dialog).findByRole("button", { name: /Bina Shah/ }, { timeout: 5000 })); // 1
    expect(within(dialog).getByRole("radio", { name: /next token 2, 11 left/ })).toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm booking" })); // 2

    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onDone.mock.calls[0]?.[1]).toMatch(/^Bina Shah booked: .*, token 2\.$/);
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
      session_id: session().id,
      patient_id: PATIENT_ID,
      source: "FRONT_DESK",
    });
  });

  it("R3: in slot mode offers free slots only and sends the chosen one", async () => {
    const s = slotSession();
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/sessions": () => json(200, { items: [s] }),
      "POST /api/v1/appointments": () => json(201, { token_number: null, slot_start: s.slots[3]?.starts_at, on_date: s.on_date }),
    });
    renderInWorkspace(
      <BookDrawer
        target={{ kind: "book", patient: patient() }}
        doctors={[doctor()]}
        doctorId={doctor().id}
        date={s.on_date}
        onDone={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const dialog = await screen.findByRole("dialog", { name: "Book appointment" }, { timeout: 5000 });
    const slots = await within(dialog).findAllByRole("radio");
    expect(slots).toHaveLength(2);
    expect(slots[0]).toBeChecked();
    fireEvent.click(slots[1] as HTMLElement);
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm booking" }));

    await waitFor(() => expect(api.count("POST /api/v1/appointments")).toBe(1));
    expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({ slot_start: s.slots[3]?.starts_at });
  });

  it("FR-APT-04: a place taken meanwhile shows the API's message and reloads the day", async () => {
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/sessions": () => json(200, { items: [session()] }),
      "POST /api/v1/appointments": () => apiError(409, "APT_SESSION_FULL", "This session is full."),
    });
    renderInWorkspace(
      <BookDrawer target={{ kind: "book", patient: patient() }} doctors={[doctor()]} doctorId={doctor().id} date={session().on_date} onDone={vi.fn()} onClose={vi.fn()} />,
    );
    const dialog = await screen.findByRole("dialog", { name: "Book appointment" }, { timeout: 5000 });
    await within(dialog).findByRole("radio");
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm booking" }));

    expect(await within(dialog).findByText("This session is full.")).toBeInTheDocument();
    await waitFor(() => expect(api.count("GET /api/v1/sessions")).toBe(2));
  });
});

describe("a patient's appointments (D32)", () => {
  it("lists them with the doctor, and offers Book for the patient", async () => {
    mockApi({
      ...boardRoutes,
      [`GET /api/v1/patients/${PATIENT_ID}/appointments`]: () =>
        json(200, { items: [{ id: "a1", on_date: "2026-10-19", doctor_id: doctor().id, token_number: 3, slot_start: null, status: "COMPLETED" }] }),
    });
    renderInWorkspace(<PatientAppointments patient={patient()} />);

    const table = await screen.findByRole("table");
    expect(table).toHaveTextContent(/Mon, 19 Oct.*Dr Meera Iyer.*Token 3.*Completed/);
    expect(screen.getByRole("button", { name: "Book for Bina Shah" })).toBeInTheDocument();
  });
});
