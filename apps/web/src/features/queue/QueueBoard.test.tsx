import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { push, resetNavigation } from "@/test/navigation";

import { QueueBoard, initialDoctor } from "./QueueBoard";
import { OTHER_DOCTOR_ID, DOCTOR_ID, boardRoutes, deskWithQueue, doctor, queueOf } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const FIRST = "0192f0a0-0000-7000-8000-000000000100";
const TRANSITION = `POST /api/v1/appointments/${FIRST}/transitions`;

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

const queueRoute = (q: ReturnType<typeof queueOf>) => () => json(200, q, { ETag: '"t1"' });

async function board() {
  renderInWorkspace(<QueueBoard />);
  return screen.findByRole("table", {}, { timeout: 5000 });
}

describe("queue board (M3-P5, FR-QUE-01)", () => {
  it("lists the day in token order with one named next step per row", async () => {
    mockApi({
      ...boardRoutes,
      "GET /api/v1/queue": queueRoute(queueOf([{}, { status: "ARRIVED" }])),
    });
    const table = await board();

    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent(/Token 1.*Asha Rao.*SC-0001.*Booked/);
    expect(rows[1]).toHaveTextContent(/Token 2.*Patient 2.*Arrived.*under 1 min/);
    expect(within(rows[0] as HTMLElement).getByRole("button", { name: "Mark Asha Rao arrived" })).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByRole("button", { name: "Start Patient 2's consultation" })).toBeInTheDocument();
  });

  it("D18, D29: a step sends the status the row showed and reports who and when", async () => {
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/queue": queueRoute(queueOf([{}])),
      [TRANSITION]: () => json(200, {}),
    });
    await board();

    fireEvent.click(screen.getByRole("button", { name: "Mark Asha Rao arrived" }));

    await waitFor(() => expect(screen.getByText(/^Asha Rao marked arrived at \d\d:\d\d\.$/)).toBeInTheDocument());
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ from: "BOOKED", to: "ARRIVED" });
  });

  it("D18: when another screen moved first, says so and refreshes", async () => {
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/queue": queueRoute(queueOf([{}])),
      [TRANSITION]: () =>
        apiError(409, "QUE_INVALID_TRANSITION", "That status change isn't allowed.", {}, { from: "ARRIVED", to: "ARRIVED" }),
    });
    await board();
    const before = api.count("GET /api/v1/queue");

    fireEvent.click(screen.getByRole("button", { name: "Mark Asha Rao arrived" }));

    expect(await screen.findByText(/Someone else already updated Asha Rao: now arrived/)).toBeInTheDocument();
    await waitFor(() => expect(api.count("GET /api/v1/queue")).toBeGreaterThan(before));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("D29: No-show asks first; going back sends nothing", async () => {
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/queue": queueRoute(queueOf([{}])),
      [TRANSITION]: () => json(200, {}),
    });
    await board();

    fireEvent.click(screen.getByRole("button", { name: "More actions for Asha Rao" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "No-show…" }));
    const dialog = screen.getByRole("dialog", { name: "Mark Asha Rao as a no-show?" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Go back" }));
    expect(api.count(TRANSITION)).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: "More actions for Asha Rao" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "No-show…" }));
    fireEvent.click(screen.getByRole("button", { name: "Mark no-show" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ from: "BOOKED", to: "NO_SHOW" }));
  });

  it("D14: Cancel needs a reason, and OTHER a note", async () => {
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/queue": queueRoute(queueOf([{}])),
      [`POST /api/v1/appointments/${FIRST}/cancel`]: () => json(200, {}),
    });
    await board();

    fireEvent.click(screen.getByRole("button", { name: "More actions for Asha Rao" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Cancel…" }));
    const dialog = screen.getByRole("dialog", { name: "Cancel Asha Rao's appointment" });
    const submit = within(dialog).getByRole("button", { name: "Cancel appointment" });
    expect(submit).toBeDisabled();
    fireEvent.click(within(dialog).getByLabelText("Other (say why)"));
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Note/), { target: { value: "moved city" } });
    fireEvent.click(submit);

    expect(await screen.findByText("Asha Rao's appointment cancelled.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ reason: "OTHER", note: "moved city" });
  });

  it("D27: a doctor opens on their own day; the picker remembers another choice", async () => {
    const doctors = [doctor(), doctor({ id: OTHER_DOCTOR_ID, display_name: "Dr Own", user_id: "u-1" })];
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/me": () => json(200, person([deskWithQueue])),
      "GET /api/v1/clinic/doctors": () => json(200, { items: doctors }),
      "GET /api/v1/queue": queueRoute({ on_date: "2026-10-19", sessions: [] }),
    });
    renderInWorkspace(<QueueBoard />);

    await waitFor(() =>
      expect(api.calls.some((c) => c.path === "/api/v1/queue" && c.search.get("doctor_id") === OTHER_DOCTOR_ID)).toBe(true),
    );
    fireEvent.change(screen.getByLabelText("Doctor"), { target: { value: DOCTOR_ID } });
    expect(window.localStorage.getItem(`mediease.queue.doctor.${deskWithQueue.clinic_id}`)).toBe(DOCTOR_ID);
  });

  it("initialDoctor prefers the doctor's own profile, then the remembered one, then the first", () => {
    const a = doctor();
    const b = doctor({ id: OTHER_DOCTOR_ID, user_id: "me" });
    const gone = doctor({ id: "x", is_active: false });
    expect(initialDoctor([a, b], "me", DOCTOR_ID)).toBe(OTHER_DOCTOR_ID);
    expect(initialDoctor([a, b], "other", OTHER_DOCTOR_ID)).toBe(OTHER_DOCTOR_ID);
    expect(initialDoctor([gone, a], "other", "x")).toBe(DOCTOR_ID);
    expect(initialDoctor([gone], "other", null)).toBeUndefined();
  });

  it("D28: another day hides the queue steps but keeps booking", async () => {
    const q = queueOf([{}]);
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/queue": (call) =>
        json(200, call.search.get("date") === q.on_date ? q : { on_date: call.search.get("date"), sessions: [] }),
    });
    await board();
    fireEvent.click(screen.getByRole("button", { name: "Next day" }));

    expect(await screen.findByText(/No sessions for this doctor/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Book" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add walk-in" })).not.toBeInTheDocument();
    expect(api.calls.at(-1)?.search.get("date")).not.toBe(q.on_date);
  });
});

// M4-P6: the doctor's own rows open the consultation; front desk prints an issued prescription.
const VISIT_ID = "0192f0a0-0000-7000-8000-0000000002a1";
const RX_ID = "0192f0a0-0000-7000-8000-0000000003b1";
const doctorMember = membership(CLINIC_A, "Alpha Clinic", "DOCTOR", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "QUEUE_MOVE", "CLINICAL_VIEW", "CLINICAL_WRITE", "RX_PRINT"],
});
const deskPrinting = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", {
  permissions: [...deskWithQueue.permissions, "RX_PRINT"],
});
const issued = { id: RX_ID, version: 1, issued_at: "2026-10-18T05:00:00+00:00" };

describe("queue board and the consultation (M4-P6)", () => {
  const asDoctor = {
    ...boardRoutes,
    "GET /api/v1/me": () => json(200, person([doctorMember])),
    "GET /api/v1/clinic/doctors": () => json(200, { items: [doctor({ user_id: "u-1" })] }),
  };

  it("journey 1: the doctor's Start moves the row, starts the visit and opens the screen", async () => {
    const api = mockApi({
      ...asDoctor,
      "GET /api/v1/queue": queueRoute(queueOf([{ status: "ARRIVED" }])),
      [TRANSITION]: () => json(200, {}),
      "POST /api/v1/visits": () => json(201, { id: VISIT_ID }),
    });
    await board();

    fireEvent.click(screen.getByRole("button", { name: "Start Asha Rao's consultation" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/visits/${VISIT_ID}`));
    expect(api.calls.find((c) => c.path === "/api/v1/visits")?.body).toEqual({ appointment_id: FIRST });
  });

  it("a second start reopens the existing visit (VIS_ALREADY_EXISTS)", async () => {
    mockApi({
      ...asDoctor,
      "GET /api/v1/queue": queueRoute(queueOf([{ status: "ARRIVED" }])),
      [TRANSITION]: () => json(200, {}),
      "POST /api/v1/visits": () =>
        apiError(409, "VIS_ALREADY_EXISTS", "This consultation already has a visit", {}, { visit_id: VISIT_ID }),
    });
    await board();

    fireEvent.click(screen.getByRole("button", { name: "Start Asha Rao's consultation" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/visits/${VISIT_ID}`));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("in consultation, the doctor's row opens the visit; completing moves to the menu", async () => {
    const api = mockApi({
      ...asDoctor,
      "GET /api/v1/queue": queueRoute(queueOf([{ status: "IN_CONSULTATION" }], "Asha Rao", [{ visit_id: VISIT_ID }])),
    });
    await board();

    expect(screen.queryByRole("button", { name: "Complete Asha Rao's consultation" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open Asha Rao's consultation" }));
    expect(push).toHaveBeenCalledWith(`/visits/${VISIT_ID}`);
    expect(api.count("POST /api/v1/visits")).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: "More actions for Asha Rao" }));
    expect(screen.getByRole("menuitem", { name: "Mark completed" })).toBeInTheDocument();
  });

  it("FR-VIS-05: the doctor's Mark completed completes the visit, which completes the row", async () => {
    const api = mockApi({
      ...asDoctor,
      "GET /api/v1/queue": queueRoute(queueOf([{ status: "IN_CONSULTATION" }], "Asha Rao", [{ visit_id: VISIT_ID }])),
      [`POST /api/v1/visits/${VISIT_ID}/complete`]: () => json(200, { id: VISIT_ID }),
    });
    await board();

    fireEvent.click(screen.getByRole("button", { name: "More actions for Asha Rao" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Mark completed" }));

    expect(await screen.findByText(/^Asha Rao marked completed at \d\d:\d\d\.$/)).toBeInTheDocument();
    expect(api.count(TRANSITION)).toBe(0);
  });

  it("another doctor's row keeps the plain queue step", async () => {
    mockApi({
      ...asDoctor,
      "GET /api/v1/clinic/doctors": () => json(200, { items: [doctor({ user_id: "someone-else" })] }),
      "GET /api/v1/queue": queueRoute(queueOf([{ status: "IN_CONSULTATION" }], "Asha Rao", [{ visit_id: VISIT_ID }])),
    });
    await board();

    expect(screen.getByRole("button", { name: "Complete Asha Rao's consultation" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open Asha Rao's consultation" })).not.toBeInTheDocument();
  });

  it("P2 6A, D6: front desk sees 'Prescription issued' and prints it, with no clinical content", async () => {
    const pdf = new Blob(["%PDF-1.7"], { type: "application/pdf" });
    const tab = { location: { href: "" }, close: vi.fn() };
    const opened = vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    const created = vi.fn(() => "blob:rx");
    Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() });
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/me": () => json(200, person([deskPrinting])),
      "GET /api/v1/queue": queueRoute(
        queueOf([{ status: "COMPLETED" }], "Asha Rao", [{ visit_id: VISIT_ID, prescription: issued }]),
      ),
      [`GET /api/v1/prescriptions/${RX_ID}/pdf`]: () => new Response(pdf, { status: 200, headers: { "Content-Type": "application/pdf" } }),
    });
    const table = await board();

    const row = within(table).getAllByRole("row")[1] as HTMLElement;
    expect(row).toHaveTextContent(/Completed\s*Prescription issued/);
    expect(within(row).queryByRole("button", { name: /Open/ })).not.toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: "More actions for Asha Rao" }));
    expect(screen.queryByRole("menuitem", { name: "Open consultation" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: "Print prescription" }));

    await waitFor(() => expect(tab.location.href).toBe("blob:rx"));
    expect(opened).toHaveBeenCalledWith("", "_blank");
    expect(api.count(`GET /api/v1/prescriptions/${RX_ID}/pdf`)).toBe(1);
    opened.mockRestore();
  });
});

describe("queue board live link (M6b-P6, R69)", () => {
  it("Copy live link copies the appointment's link and says whose it is", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const url = "https://example.test/q/signed-token";
    const api = mockApi({
      ...boardRoutes,
      "GET /api/v1/queue": queueRoute(queueOf([{}])),
      [`GET /api/v1/appointments/${FIRST}/live-link`]: () => json(200, { url, expires_at: "2026-10-22T14:30:00Z" }),
    });
    await board();

    fireEvent.click(screen.getByRole("button", { name: "More actions for Asha Rao" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Copy live link" }));

    expect(await screen.findByText("Live link for Asha Rao copied. It works until the session ends.")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith(url);
    expect(api.count(`GET /api/v1/appointments/${FIRST}/live-link`)).toBe(1);
  });

  it("a completed row has no live link", async () => {
    mockApi({ ...boardRoutes, "GET /api/v1/queue": queueRoute(queueOf([{ status: "COMPLETED" }])) });
    await board();
    const more = screen.queryByRole("button", { name: "More actions for Asha Rao" });
    if (more !== null) fireEvent.click(more);
    expect(screen.queryByRole("menuitem", { name: "Copy live link" })).not.toBeInTheDocument();
  });
});
