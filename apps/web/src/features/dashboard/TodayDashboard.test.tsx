import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { TodayDashboard } from "./TodayDashboard";
import { todayOf, weekOf } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const URL = "GET /api/v1/dashboard/today";
const owner = membership(CLINIC_A, "Alpha Clinic", "OWNER", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "USAGE_METRICS_VIEW"],
});
const doctorMember = membership(CLINIC_A, "Alpha Clinic", "DOCTOR", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "USAGE_METRICS_VIEW", "CLINICAL_WRITE"],
});

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  window.history.replaceState(null, "", "/today");
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

async function shown() {
  return screen.findByRole("heading", { level: 1, name: "Today" }).then(async () => {
    await screen.findByRole("list", { name: "Today's appointments" });
  });
}

describe("Today (M6-P1)", () => {
  it("decision 5A: front desk sees the clinic's counts, each tile linking to the screen it summarises", async () => {
    mockApi({ ...workspaceRoutes, [URL]: () => json(200, todayOf(), { ETag: '"t1"' }) });

    renderInWorkspace(<TodayDashboard />);
    await shown();

    const tiles = screen.getByRole("list", { name: "Today's appointments" });
    expect(within(tiles).getByRole("link", { name: /Waiting\s*3/ })).toHaveAttribute("href", "/queue");
    expect(within(tiles).getByRole("link", { name: /No-shows\s*1/ })).toHaveAttribute("href", "/queue");
    expect(within(tiles).getByRole("link", { name: /Completed\s*4/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Follow-ups due\s*2/ })).toHaveAttribute("href", "/follow-ups");
    expect(screen.getByText("Messages failed today").closest("li")).toHaveTextContent("1");
    // Not for front desk: there is no 7-day view.
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("lists who is next by token or slot time, with the first name and code only", async () => {
    mockApi({ ...workspaceRoutes, [URL]: () => json(200, todayOf()) });

    renderInWorkspace(<TodayDashboard />);
    await shown();

    const next = screen.getByRole("region", { name: "Next up" });
    const rows = within(next).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Token 4");
    expect(rows[0]).toHaveTextContent("Asha SC-0004");
    expect(rows[0]).toHaveTextContent("Waiting");
    expect(rows[1]).toHaveTextContent("10:30"); // 05:00 UTC on the clinic's (Kolkata) clock
    expect(rows[1]).toHaveTextContent("Not arrived");
    const sessions = screen.getByRole("region", { name: "Sessions" });
    expect(sessions).toHaveTextContent("Dr Meera Iyer");
    expect(sessions).toHaveTextContent("10:00–13:00");
    expect(sessions).toHaveTextContent("11 of 20 booked · 3 waiting · 4 completed");
  });

  it("a quiet day says so instead of showing an empty list", async () => {
    mockApi({
      ...workspaceRoutes,
      [URL]: () =>
        json(200, todayOf({ sessions: [], next_patients: [], counts: { total: 0, not_arrived: 0, waiting: 0, in_consultation: 0, completed: 0, no_show: 0 } })),
    });

    renderInWorkspace(<TodayDashboard />);
    await shown();

    expect(screen.getByText("No one is waiting")).toBeInTheDocument();
    expect(screen.getByText("No sessions today")).toBeInTheDocument();
  });

  it("a doctor sees their own sessions and no clinic message count", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, person([doctorMember])),
      [URL]: () => json(200, todayOf({ scope: "DOCTOR", messages_failed: null, week: weekOf() })),
    });

    renderInWorkspace(<TodayDashboard />);
    await shown();

    expect(screen.getByText(/· Your sessions$/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Your sessions" })).toBeInTheDocument();
    expect(screen.queryByText("Messages failed today")).not.toBeInTheDocument();
  });

  it("owners get the last 7 days in a second tab, reachable with the keyboard", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, person([owner])),
      [URL]: () =>
        json(200, todayOf({ week: weekOf((i) => (i === 4 ? { appointments: 8, completed: 6, no_show: 2, messages_sent: 5 } : {})) })),
    });

    renderInWorkspace(<TodayDashboard />);
    await shown();

    const tabs = screen.getByRole("tablist", { name: "Views of the day" });
    const todayTab = within(tabs).getByRole("tab", { name: "Today" });
    expect(todayTab).toHaveAttribute("aria-selected", "true");

    todayTab.focus();
    fireEvent.keyDown(todayTab, { key: "ArrowRight" });
    const weekTab = within(tabs).getByRole("tab", { name: "Last 7 days" });
    await waitFor(() => expect(weekTab).toHaveAttribute("aria-selected", "true"));

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(8); // the header and seven days
    expect(rows[5]).toHaveTextContent("8625%5"); // 8 appointments, 6 completed, 25% no-shows, 5 sent
  });

  it("shows a skeleton while loading, then the numbers", async () => {
    let answer: (r: Response) => void = () => {};
    mockApi({ ...workspaceRoutes, [URL]: () => new Promise<Response>((resolve) => (answer = resolve)) });

    renderInWorkspace(<TodayDashboard />);

    expect(await screen.findByText("Loading today…")).toHaveAttribute("role", "status");
    answer(json(200, todayOf()));
    await shown();
  });

  it("the API down shows the error with its Ref, and Try again loads the day", async () => {
    let up = false;
    mockApi({
      ...workspaceRoutes,
      [URL]: () => (up ? json(200, todayOf()) : apiError(503, "SYS_UNAVAILABLE", "The service is unavailable.")),
    });

    renderInWorkspace(<TodayDashboard />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Ref: test-ref");
    up = true;
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    await shown();
  });
});
