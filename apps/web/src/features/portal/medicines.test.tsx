import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi } from "@/test/api";
import { navigation, resetNavigation } from "@/test/navigation";

import { PortalMedicines } from "./Medicines";
import { PortalAccountPage } from "./PortalAccountPage";
import { CLINIC_ID, PORTAL_ACCOUNT, link, me, renderPortal } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const RX_ID = "0192f0a0-0000-7000-8000-0000000003c1";
const TAB_ID = "0192f0a0-0000-7000-8000-0000000005d1";
const SYRUP_ID = "0192f0a0-0000-7000-8000-0000000005d2";

const CONTEXT = {
  prescription_id: RX_ID,
  version: 1,
  clinic_id: CLINIC_ID,
  clinic_name: "Sample Clinic",
  clinic_phone_e164: "+919000000010",
  doctor_name: "Dr. Sample Doctor",
  starts_on: "2026-10-25",
  timezone: "Asia/Kolkata",
};
const TAB = {
  ...CONTEXT,
  item_id: TAB_ID,
  medicine_name: "Tab Sample",
  form_strength: null,
  dose: "1 tablet",
  as_written: null,
  timing: "After food",
  how: "Take with water",
  duration: "5 days",
  day: 1,
  days_total: 5,
  reminder: { enabled: false, remind_at: null },
  mark: { status: "UPCOMING", marked_at: null, markable: true },
};
const SYRUP = {
  ...CONTEXT,
  item_id: SYRUP_ID,
  medicine_name: "Syrup Sample",
  form_strength: null,
  dose: "5 ml",
  as_written: "Only when needed",
  timing: null,
  how: null,
  duration: "Ongoing — as prescribed",
  day: 1,
  days_total: null,
  reminder: null,
  mark: null,
};

function plan(overrides: Record<string, unknown> = {}) {
  return {
    date: "2026-10-25",
    today: "2026-10-25",
    language: "en",
    has_prescriptions: true,
    slots: [
      { slot: "MORNING", label: "Morning", time: "08:00", entries: [TAB] },
      { slot: "AFTERNOON", label: "Afternoon", time: "14:00", entries: [TAB] },
    ],
    as_written: [SYRUP],
    ...overrides,
  };
}

function course(overrides: Record<string, unknown> = {}) {
  const { day, days_total, reminder, mark, ...tab } = TAB;
  void day;
  void days_total;
  void reminder;
  void mark;
  return {
    ...CONTEXT,
    revised: false,
    reminders_set: false,
    ends_on: null,
    lines: [
      {
        ...tab,
        ends_on: "2026-10-29",
        slots: [
          { slot: "MORNING", label: "Morning", time: "08:00", reminder: { enabled: false, remind_at: null } },
          { slot: "AFTERNOON", label: "Afternoon", time: "14:00", reminder: { enabled: false, remind_at: null } },
        ],
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  navigation.pathname = "/portal/medicines";
  document.cookie = "me_pt_csrf=portal-csrf; path=/";
});

afterEach(() => {
  document.cookie = "me_pt_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("My medicines (M6b-P3, spec R28-R44)", () => {
  it("R36, R37: today by time of day with the API's words, then as written, the safety line and the call", async () => {
    mockApi({ ...me(), "GET /api/v1/portal/medicine-plan": () => json(200, plan()) });
    await renderPortal(<PortalMedicines />);
    const morning = await screen.findByRole("region", { name: "Morning · 08:00" });
    expect(within(morning).getByText("Tab Sample")).toBeInTheDocument();
    expect(within(morning).getByText("After food · Take with water")).toBeInTheDocument();
    expect(within(morning).getByText("Day 1 of 5 · Dr. Sample Doctor · Sample Clinic")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Afternoon · 14:00" })).toBeInTheDocument();
    const asWritten = screen.getByRole("region", { name: "As the doctor wrote" });
    expect(within(asWritten).getByText("Only when needed")).toBeInTheDocument();
    expect(screen.getByText(/This plan only lays out your prescription/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contact your clinic" })).toHaveAttribute("href", "tel:+919000000010");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("R44: no current prescription says so, still with the safety line", async () => {
    mockApi({ ...me(), "GET /api/v1/portal/medicine-plan": () => json(200, plan({ has_prescriptions: false, slots: [], as_written: [] })) });
    await renderPortal(<PortalMedicines />);
    expect(await screen.findByText("No medicines from your prescriptions yet.")).toBeInTheDocument();
    expect(screen.getByText(/This plan only lays out your prescription/)).toBeInTheDocument();
  });

  it("moves a day at a time and asks the API for that date", async () => {
    const api = mockApi({ ...me(), "GET /api/v1/portal/medicine-plan": () => json(200, plan()) });
    await renderPortal(<PortalMedicines />);
    fireEvent.click(await screen.findByRole("button", { name: "Next day" }));
    await waitFor(() => expect(api.calls.some((c) => c.search.get("date") === "2026-10-26")).toBe(true));
  });

  it("R38, R39: a reminder choice per line and slot, saved through the session; a revision asks again", async () => {
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/medicine-plan": () => json(200, plan()),
      "GET /api/v1/portal/medicine-plan/courses": () => json(200, { items: [course({ version: 2, revised: true })] }),
      "PUT /api/v1/portal/medicine-plan/reminders": (call) => {
        const body = call.body as { enabled: boolean; remind_at: string | null };
        return json(200, { enabled: body.enabled, remind_at: body.remind_at });
      },
    });
    await renderPortal(<PortalMedicines />);
    fireEvent.click(await screen.findByRole("button", { name: "Courses" }));
    expect(await screen.findByText("This prescription was updated — set your reminders again.")).toBeInTheDocument();
    expect(screen.getByText("From 25 Oct 2026")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("checkbox", { name: "Remind me · Morning (08:00)" }));
    await waitFor(() => expect(api.calls.filter((c) => c.method === "PUT")).toHaveLength(1));
    const first = api.calls.find((c) => c.method === "PUT");
    expect(first?.body).toEqual({ prescription_id: RX_ID, item_id: TAB_ID, slot: "MORNING", enabled: true, remind_at: null });
    expect(first?.headers.get("X-CSRF-Token")).toBe("portal-csrf");

    const time = await screen.findByLabelText("Reminder time, Morning");
    fireEvent.change(time, { target: { value: "07:30" } });
    fireEvent.click(screen.getByRole("button", { name: "Save time" }));
    await waitFor(() => expect(api.calls.filter((c) => c.method === "PUT")).toHaveLength(2));
    expect(api.calls.filter((c) => c.method === "PUT")[1]?.body).toMatchObject({ enabled: true, remind_at: "07:30" });
    expect(await screen.findByText("Your reminder choice is saved.")).toBeInTheDocument();
  });

  it("R42: the planner's own words in Hindi", async () => {
    mockApi({ ...me({ language: "hi" }), "GET /api/v1/portal/medicine-plan": () => json(200, plan({ language: "hi" })) });
    await renderPortal(<PortalMedicines />);
    expect(await screen.findByRole("heading", { name: "मेरी दवाइयाँ" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "अपने क्लिनिक से संपर्क करें" })).toBeInTheDocument();
  });

  it("R29: the screen never reads a frequency; the API's plan is all it shows", () => {
    const source = readFileSync(join(process.cwd(), "src", "features", "portal", "Medicines.tsx"), "utf8");
    expect(source).not.toMatch(/frequency|slot_sets|"1-0-1"/);
  });
});

describe("Dose marks (M6b-P3b, R45-R48)", () => {
  it("R45, R46: Taken, then Change to Skipped, through the session; only Contact your clinic is said", async () => {
    let state = "TAKEN";
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/medicine-plan": () => json(200, plan()),
      "PUT /api/v1/portal/medicine-plan/doses": (call) => {
        state = (call.body as { state: string }).state;
        return json(200, { status: state, marked_at: "2026-10-25T02:42:00Z", markable: true });
      },
    });
    await renderPortal(<PortalMedicines />);
    const morning = await screen.findByRole("region", { name: "Morning · 08:00" });
    expect(within(morning).getByText("Upcoming")).toBeInTheDocument();
    fireEvent.click(within(morning).getByRole("button", { name: "Taken: Tab Sample, Morning" }));
    expect(await within(morning).findByText(/^Taken at 8:12/)).toBeInTheDocument();
    const first = api.calls.find((c) => c.method === "PUT");
    expect(first?.body).toEqual({ prescription_id: RX_ID, item_id: TAB_ID, on_date: "2026-10-25", slot: "MORNING", state: "TAKEN" });
    expect(first?.headers.get("X-CSRF-Token")).toBe("portal-csrf");
    expect(within(morning).queryByText(/contact your clinic/)).not.toBeInTheDocument();

    fireEvent.click(within(morning).getByRole("button", { name: "Change" }));
    fireEvent.click(within(morning).getByRole("button", { name: "Skipped: Tab Sample, Morning" }));
    expect(await within(morning).findByText(/^Skipped at 8:12/)).toBeInTheDocument();
    expect(within(morning).getByText(/If you are unsure what to do, contact your clinic/)).toBeInTheDocument();
    expect(within(morning).getByRole("link", { name: "Contact your clinic" })).toHaveAttribute("href", "tel:+919000000010");
  });

  it("R46, R47: an unmarked past dose outside its window is Not recorded, with no buttons", async () => {
    const old = { ...TAB, mark: { status: "NOT_RECORDED", marked_at: null, markable: false } };
    mockApi({ ...me(), "GET /api/v1/portal/medicine-plan": () => json(200, plan({ slots: [{ slot: "MORNING", label: "Morning", time: "08:00", entries: [old] }] })) });
    await renderPortal(<PortalMedicines />);
    const morning = await screen.findByRole("region", { name: "Morning · 08:00" });
    expect(within(morning).getByText("Not recorded")).toBeInTheDocument();
    expect(within(morning).queryByRole("button", { name: /^Taken/ })).not.toBeInTheDocument();
    expect(within(morning).getByText(/If you are unsure what to do, contact your clinic/)).toBeInTheDocument();
  });

  it("R47, R49: the history lists each day with counts, never a score", async () => {
    mockApi({
      ...me(),
      "GET /api/v1/portal/medicine-plan": () => json(200, plan()),
      "GET /api/v1/portal/medicine-plan/courses": () => json(200, { items: [course()] }),
      "GET /api/v1/portal/medicine-plan/history": () =>
        json(200, {
          prescription_id: RX_ID,
          version: 1,
          clinic_name: "Sample Clinic",
          clinic_phone_e164: "+919000000010",
          timezone: "Asia/Kolkata",
          starts_on: "2026-10-24",
          counts: { TAKEN: 1, SKIPPED: 0, NOT_RECORDED: 1, UPCOMING: 2 },
          days: [
            { date: "2026-10-24", doses: [
              { item_id: TAB_ID, medicine_name: "Tab Sample", dose: "1 tablet", slot: "MORNING", status: "TAKEN", marked_at: "2026-10-24T02:42:00Z" },
              { item_id: TAB_ID, medicine_name: "Tab Sample", dose: "1 tablet", slot: "AFTERNOON", status: "NOT_RECORDED", marked_at: null },
            ] },
          ],
          versions: [{ prescription_id: RX_ID, version: 1, status: "ISSUED" }],
        }),
    });
    await renderPortal(<PortalMedicines />);
    fireEvent.click(await screen.findByRole("button", { name: "Courses" }));
    fireEvent.click(await screen.findByRole("button", { name: "History" }));
    const history = await screen.findByRole("region", { name: "History · version 1" });
    expect(within(history).getByText("Taken 1 · Skipped 0 · Not recorded 1")).toBeInTheDocument();
    expect(within(history).getByText(/Morning · Tab Sample \(1 tablet\): Taken at 8:12/)).toBeInTheDocument();
    expect(within(history).getByText(/Afternoon · Tab Sample \(1 tablet\): Not recorded/)).toBeInTheDocument();
    expect(within(history).queryByText(/%/)).not.toBeInTheDocument();
  });
});

describe("Account: times of day (R34)", () => {
  it("refuses times out of order without calling the API, then saves them", async () => {
    const times = { morning: "07:00", afternoon: "13:00", evening: "18:00", night: "22:00" };
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/links": () => json(200, { items: [link()] }),
      "PATCH /api/v1/portal/me": () => json(200, { account: { ...PORTAL_ACCOUNT, slot_times: times } }),
    });
    await renderPortal(<PortalAccountPage />);
    const morning = await screen.findByLabelText("Morning");
    expect(morning).toHaveValue("08:00");
    fireEvent.change(morning, { target: { value: "15:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save times" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Each time must be later than the one before");
    expect(api.calls.some((c) => c.method === "PATCH")).toBe(false);

    fireEvent.change(morning, { target: { value: "07:00" } });
    fireEvent.change(screen.getByLabelText("Afternoon"), { target: { value: "13:00" } });
    fireEvent.change(screen.getByLabelText("Night"), { target: { value: "22:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save times" }));
    expect(await screen.findByText("Your times of day are saved.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ slot_times: times });
  });
});
