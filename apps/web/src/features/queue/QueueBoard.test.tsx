import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { person } from "@/features/auth/testing";
import { renderInWorkspace } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

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
