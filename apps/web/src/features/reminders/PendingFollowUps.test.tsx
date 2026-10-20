import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PATIENT_ID, renderInWorkspace } from "@/features/patients/testing";
import { DOCTOR_ID, SESSION_ID, appointment, session, today } from "@/features/queue/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { PendingFollowUps } from "./PendingFollowUps";
import { pending, reminderRoutes } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const PENDING = "GET /api/v1/follow-ups/pending";

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

const heading = () => screen.findByRole("heading", { level: 1, name: "Pending follow-ups" }, { timeout: 5000 });

describe("pending follow-ups (FR-REM-07, R17; M5-P6 decision 4A)", () => {
  it("lists overdue patients with the date, doctor and reminder status, linked to the profile", async () => {
    const api = mockApi({ ...reminderRoutes, [PENDING]: () => json(200, { items: [pending()], limit: 50, offset: 0 }) });
    renderInWorkspace(<PendingFollowUps />);
    await heading();

    const row = await screen.findByRole("row", { name: /Bina Shah/ });
    expect(row).toHaveTextContent("SC-0004");
    expect(row).toHaveTextContent("Sat, 17 Oct");
    expect(row).toHaveTextContent("Dr Meera Iyer");
    expect(row).toHaveTextContent("Delivered");
    expect(within(row).getByRole("link", { name: "Bina Shah" })).toHaveAttribute("href", `/patients/${PATIENT_ID}`);
    expect(within(row).getByRole("button")).toHaveAccessibleName("Book follow-up for Bina Shah");
    const call = api.calls.find((c) => c.path === "/api/v1/follow-ups/pending");
    expect([call?.search.get("limit"), call?.search.get("offset")]).toEqual(["50", "0"]);
    expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  });

  it("Book follow-up opens the drawer with the patient, the doctor and today chosen; Confirm books it", async () => {
    const api = mockApi({
      ...reminderRoutes,
      [PENDING]: () => json(200, { items: [pending()], limit: 50, offset: 0 }),
      "GET /api/v1/sessions": () => json(200, { items: [session()] }),
      "POST /api/v1/appointments": () => json(201, appointment({ token_number: 2 })),
    });
    renderInWorkspace(<PendingFollowUps />);
    await heading();

    fireEvent.click(await screen.findByRole("button", { name: "Book follow-up for Bina Shah" }, { timeout: 5000 })); // 1
    const dialog = await screen.findByRole("dialog", { name: "Book appointment" });
    expect(dialog).toHaveTextContent("Bina Shah · SC-0004");
    expect(within(dialog).getByLabelText("Doctor")).toHaveValue(DOCTOR_ID);
    expect(within(dialog).getByLabelText("Date")).toHaveValue(today());
    const confirm = within(dialog).getByRole("button", { name: "Confirm booking" });
    await waitFor(() => expect(confirm).toBeEnabled());
    fireEvent.click(confirm); // 2

    expect(await screen.findByText(/Bina Shah booked: .*token 2\./)).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
      session_id: SESSION_ID,
      patient_id: PATIENT_ID,
      source: "FRONT_DESK",
    });
    const row = screen.getByRole("row", { name: /Bina Shah/ });
    expect(row).toHaveTextContent("Booked");
    expect(within(row).queryByRole("button", { name: /Book follow-up/ })).not.toBeInTheDocument();
  }, 15_000);

  it("Show more loads the next page when a page was full", async () => {
    const page = (offset: number, n: number) =>
      Array.from({ length: n }, (_, i) =>
        pending({ patient_id: `p-${offset + i}`, patient_name: `Patient ${offset + i}`, patient_code: `SC-${offset + i}` }),
      );
    const api = mockApi({
      ...reminderRoutes,
      [PENDING]: (call) => {
        const offset = Number(call.search.get("offset"));
        return json(200, { items: page(offset, offset === 0 ? 50 : 2), limit: 50, offset });
      },
    });
    renderInWorkspace(<PendingFollowUps />);
    await heading();

    fireEvent.click(await screen.findByRole("button", { name: "Show more" }, { timeout: 5000 }));
    expect(await screen.findByRole("row", { name: /Patient 51/ }, { timeout: 5000 })).toBeInTheDocument();
    expect(api.calls.at(-1)?.search.get("offset")).toBe("50");
    expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  }, 15_000);

  it("says so when nothing is overdue, and a failure shows the Ref", async () => {
    mockApi({ ...reminderRoutes, [PENDING]: [() => apiError(503, "SYS_UNAVAILABLE", "Try again shortly."), () => json(200, { items: [], limit: 50, offset: 0 })] });
    renderInWorkspace(<PendingFollowUps />);
    await heading();

    expect(await screen.findByRole("alert")).toHaveTextContent("Ref: test-ref");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No follow-ups are overdue.")).toBeInTheDocument();
  });
});
