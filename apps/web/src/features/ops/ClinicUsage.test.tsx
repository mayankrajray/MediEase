import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { CLINIC_A, CLINIC_B, ops } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { ClinicUsage } from "./ClinicUsage";
import { lastActiveLabel, usageCsv, weekLabel } from "./usage";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const USAGE = "GET /api/v1/ops/clinic-usage";
const base = { "GET /api/v1/me": () => json(200, ops()) };
const zero = { patients: 0, appointments: 0, visits: 0, prescriptions: 0, bills: 0 };
const WEEKS = ["2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09"];

const counts = (visits: number, more: Partial<typeof zero> = {}) => ({ ...zero, visits, ...more });

const clinic = (overrides: Record<string, unknown> = {}) => ({
  clinic_id: CLINIC_A,
  name: "Kesar Bagh Family Clinic",
  slug: "kesar-bagh-family-clinic",
  status: "ACTIVE",
  timezone: "Asia/Kolkata",
  created_at: "2026-11-13T19:53:00+00:00",
  last_active_at: new Date().toISOString(),
  active_this_week: true,
  staff: { owners: 1, doctors: 2, front_desk: 1, members: 4, active_7d: 3 },
  totals: { patients: 20, appointments: 36, visits: 26, prescriptions: 24, bills: 26 },
  weeks: [
    { start: WEEKS[0], counts: counts(0) },
    { start: WEEKS[1], counts: counts(0) },
    { start: WEEKS[2], counts: counts(12, { prescriptions: 11, patients: 9 }) },
    { start: WEEKS[3], counts: counts(14, { prescriptions: 13, patients: 11 }) },
  ],
  health: { failed_messages_7d: 0, not_sent_7d: 0, failed_jobs_7d: 0 },
  ...overrides,
});

const usage = (clinics: unknown[]) => ({
  generated_at: "2026-11-14T10:00:00+00:00",
  weeks: WEEKS.map((start) => ({ start, end: start.replace(/\d\d$/, (d) => String(Number(d) + 6).padStart(2, "0")) })),
  summary: { clinics: clinics.length, active_clinics: 1, totals: { patients: 20, appointments: 36, visits: 26, prescriptions: 24, bills: 26 } },
  clinics,
});

function renderUsage() {
  return render(
    <SessionProvider>
      <ClinicUsage />
    </SessionProvider>,
  );
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  vi.restoreAllMocks();
});

describe("clinic usage (M9-P4, FR-OPS-03)", () => {
  it("summarises the weeks shown and lists active clinics first with their week bars and health", async () => {
    mockApi({
      ...base,
      [USAGE]: () =>
        json(
          200,
          usage([
            clinic({
              clinic_id: CLINIC_B,
              name: "Quiet Clinic",
              slug: "quiet-clinic",
              status: "ONBOARDING",
              last_active_at: null,
              active_this_week: false,
              staff: { owners: 1, doctors: 0, front_desk: 0, members: 1, active_7d: 0 },
              totals: zero,
              weeks: WEEKS.map((start) => ({ start, counts: zero })),
              health: { failed_messages_7d: 2, not_sent_7d: 0, failed_jobs_7d: 1 },
            }),
            clinic(),
          ]),
        ),
    });
    renderUsage();

    expect(await screen.findByRole("heading", { name: "Clinic usage" })).toBeInTheDocument();
    const summary = await screen.findByRole("list", { name: "All clinics, last 4 weeks" });
    expect(within(summary).getByText("1 of 2")).toBeInTheDocument();
    expect(within(summary).getByText("Visits").parentElement?.parentElement).toHaveTextContent("26");

    const rows = screen.getAllByRole("row").filter((r) => within(r).queryByRole("rowheader"));
    const first = rows[0];
    if (first === undefined) throw new Error("no clinic rows");
    expect(rows[0]).toHaveTextContent("Kesar Bagh Family Clinic"); // active first
    expect(rows[0]).toHaveTextContent("Active this week");
    expect(rows[0]).toHaveTextContent("4 people");
    expect(rows[0]).toHaveTextContent("3 active in 7 days");
    expect(rows[0]).toHaveTextContent("No problems");
    expect(within(first).getByText(/Visits by week, oldest first: 19–25 Oct: 0; .*9–15 Nov: 14/)).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent("Not used yet");
    expect(rows[1]).toHaveTextContent("Setting up");
    expect(rows[1]).toHaveTextContent("2 messages, 1 job failed");
  });

  it("opens a clinic's weeks with all-time totals and loads 8 weeks on request", async () => {
    const api = mockApi({ ...base, [USAGE]: () => json(200, usage([clinic()])) });
    renderUsage();

    await screen.findAllByText("Kesar Bagh Family Clinic");
    const details = screen.getByRole("button", { name: /Details for Kesar Bagh/ });
    expect(details).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(details);
    expect(details).toHaveAttribute("aria-expanded", "true");
    const weeks = screen.getByRole("table", { name: /records made each week/ });
    expect(within(weeks).getByRole("rowheader", { name: /9–15 Nov \(this week\)/ })).toBeInTheDocument();
    expect(within(weeks).getByRole("rowheader", { name: "All time" }).parentElement).toHaveTextContent("All time2036262426");
    expect(screen.getByRole("button", { name: /Download CSV for Kesar Bagh/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "8 weeks" }));
    await waitFor(() =>
      expect(api.calls.filter((c) => `${c.method} ${c.path}` === USAGE).at(-1)?.search.get("weeks")).toBe("8"),
    );
  });

  it("explains an empty console and offers to create the first clinic", async () => {
    mockApi({ ...base, [USAGE]: () => json(200, { ...usage([]), summary: { clinics: 0, active_clinics: 0, totals: zero } }) });
    renderUsage();
    expect(await screen.findByText("No clinics yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create clinic" })).toHaveAttribute("href", "/ops/clinics/new");
    expect(screen.getByRole("button", { name: "Download CSV" })).toBeDisabled();
  });

  it("shows what failed with a retry", async () => {
    let first = true;
    mockApi({
      ...base,
      [USAGE]: () => {
        if (first) {
          first = false;
          return apiError(500, "INTERNAL_ERROR", "Something went wrong.");
        }
        return json(200, usage([clinic()]));
      },
    });
    renderUsage();
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await screen.findAllByText("Kesar Bagh Family Clinic");
    expect(screen.getByRole("button", { name: /Details for Kesar Bagh/ })).toBeInTheDocument();
  });
});

describe("usage helpers", () => {
  it("labels weeks within and across months", () => {
    expect(weekLabel("2026-11-09")).toBe("9–15 Nov");
    expect(weekLabel("2026-10-26")).toBe("26 Oct – 1 Nov");
  });

  it("says when a clinic was last active in its own zone", () => {
    const now = new Date("2026-11-14T10:00:00Z"); // 15:30 IST
    expect(lastActiveLabel("2026-11-14T08:35:00Z", "Asia/Kolkata", now)).toBe("Today, 14:05");
    expect(lastActiveLabel("2026-11-13T13:10:00Z", "Asia/Kolkata", now)).toBe("Yesterday, 18:40");
    expect(lastActiveLabel("2026-11-11T05:00:00Z", "Asia/Kolkata", now)).toBe("3 days ago");
    expect(lastActiveLabel("2026-10-02T05:00:00Z", "Asia/Kolkata", now)).toBe("2 Oct 2026");
  });

  it("writes the usage evidence as CSV, one line per week and an all-time line, quoting names", () => {
    const data = usage([clinic({ name: 'Clinic "A", Lucknow' })]);
    const lines = usageCsv(data as never, data.clinics as never).trim().split("\n");
    expect(lines[0]).toBe("Clinic,Week starting,Week ending,Patients registered,Appointments booked,Visits,Prescriptions issued,Bills issued");
    expect(lines[4]).toBe('"Clinic ""A"", Lucknow",2026-11-09,2026-11-15,11,0,14,13,0');
    expect(lines[5]).toBe('"Clinic ""A"", Lucknow",All time,,20,36,26,24,26');
  });
});
