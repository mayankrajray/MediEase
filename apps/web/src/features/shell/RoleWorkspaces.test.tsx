import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { TodayDashboard } from "@/features/dashboard/TodayDashboard";
import { todayOf } from "@/features/dashboard/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi } from "@/test/api";
import { push, resetNavigation } from "@/test/navigation";

import { canSwitch, rememberWorkspace, resolveWorkspace } from "./workspace";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const DOCTOR_PROFILE = "0192f0a0-0000-7000-8000-0000000000d9";
const OWNER_PERMS = [
  "CLINIC_VIEW",
  "DOCTORS_VIEW",
  "PATIENTS_MANAGE",
  "REMINDERS_SCHEDULE",
  "STAFF_MANAGE",
  "SCHEDULES_MANAGE",
  "CLINICAL_VIEW",
  "USAGE_METRICS_VIEW",
  "AUDIT_VIEW",
] as const;
const owner = membership(CLINIC_A, "Alpha Clinic", "OWNER", { permissions: [...OWNER_PERMS] });
const practising = membership(CLINIC_A, "Alpha Clinic", "OWNER", {
  permissions: [...OWNER_PERMS, "CLINICAL_WRITE"],
  doctor_id: DOCTOR_PROFILE,
});
const doctor = membership(CLINIC_A, "Alpha Clinic", "DOCTOR", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "REMINDERS_SCHEDULE", "CLINICAL_VIEW", "CLINICAL_WRITE"],
  doctor_id: "0192f0a0-0000-7000-8000-0000000000d1",
});
const desk = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "REMINDERS_SCHEDULE"],
});

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  window.localStorage.clear();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

describe("workspace resolution (M6a-P6, decision 1A)", () => {
  it("comes from the role; only a practising owner may choose Doctor", () => {
    expect(resolveWorkspace(desk, "DOCTOR")).toBe("FRONT_DESK");
    expect(resolveWorkspace(doctor, null)).toBe("DOCTOR");
    expect(resolveWorkspace(owner, "DOCTOR")).toBe("OWNER"); // no profile: the choice is ignored
    expect(resolveWorkspace(practising, null)).toBe("OWNER"); // Owner by default
    expect(resolveWorkspace(practising, "DOCTOR")).toBe("DOCTOR");
    expect(resolveWorkspace(practising, "FRONT_DESK")).toBe("OWNER"); // a stale or odd value
    expect([owner, practising, doctor, desk].map(canSwitch)).toEqual([false, true, false, false]);
  });
});

function render(member: typeof owner, today = todayOf()) {
  const api = mockApi({
    ...workspaceRoutes,
    "GET /api/v1/me": () => json(200, person([member])),
    "GET /api/v1/dashboard/today": () => json(200, today),
    "GET /api/v1/clinic/staff": () => json(200, { items: [] }),
  });
  renderInWorkspace(<TodayDashboard />);
  return api;
}

const nav = () => within(screen.getByRole("navigation", { name: "Main" }));
const labels = () => nav().getAllByRole("link").map((l) => l.textContent);
const actions = () =>
  within(screen.getByRole("navigation", { name: "Quick actions" }))
    .getAllByRole("link")
    .concat(within(screen.getByRole("navigation", { name: "Quick actions" })).queryAllByRole("button"))
    .map((el) => el.textContent);

describe("each workspace's shell and home (FR-UX-04, FR-UX-05)", () => {
  it("the owner manages the clinic, with a Team tile and no switch", async () => {
    render(owner);
    await screen.findByRole("navigation", { name: "Quick actions" }, { timeout: 5000 });

    expect(labels()).toEqual(["Today", "Queue", "Patients", "Follow-ups", "Team", "Schedule", "Audit log", "Notifications"]);
    expect(actions()).toEqual(["Invite someone", "Schedule settings", "See the queue"]);
    expect(await screen.findByRole("list", { name: "Team" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "View" })).not.toBeInTheDocument();
  });

  it("the doctor works on their own day", async () => {
    render(doctor, todayOf({ scope: "DOCTOR", doctor_id: doctor.doctor_id }));
    await screen.findByRole("navigation", { name: "Quick actions" }, { timeout: 5000 });

    expect(labels()).toEqual(["Today", "My queue", "My patients", "My follow-ups", "My schedule", "Notifications"]);
    expect(actions()).toEqual(["Open my queue", "My patients", "My follow-ups"]);
    expect(screen.queryByRole("group", { name: "View" })).not.toBeInTheDocument();
  });

  it("the front desk runs the day, starting with registering a patient", async () => {
    render(desk);
    await screen.findByRole("navigation", { name: "Quick actions" }, { timeout: 5000 });

    expect(labels()).toEqual(["Today", "Queue", "Patients", "Follow-ups", "Notifications"]);
    expect(actions()).toEqual(["Book an appointment", "Add a walk-in", "Register a patient"]);
  });
});

describe("the practising owner's switch (FR-UX-06, decision 6A)", () => {
  it("switches to the Doctor view: the doctor's nav, Today for their profile, then back", async () => {
    const api = render(practising);
    const view = await screen.findByRole("group", { name: "View" }, { timeout: 5000 });
    expect(within(view).getByRole("radio", { name: "Owner" })).toBeChecked();
    expect(labels()).toContain("Team");

    fireEvent.click(within(view).getByRole("radio", { name: "Doctor" }));

    expect(await screen.findByText("Doctor view")).toBeInTheDocument();
    await waitFor(() => expect(labels()).toEqual(["Today", "My queue", "My patients", "My follow-ups", "My schedule", "Notifications"]));
    expect(push).toHaveBeenCalledWith("/today");
    await waitFor(() =>
      expect(api.calls.some((c) => c.path === "/api/v1/dashboard/today" && c.search.get("view") === "doctor")).toBe(true),
    );
    expect(window.localStorage.getItem(`mediease.workspace.${CLINIC_A}`)).toBe("DOCTOR");

    fireEvent.click(within(screen.getByRole("group", { name: "View" })).getByRole("radio", { name: "Owner" }));
    await waitFor(() => expect(labels()).toContain("Team"));
  });

  it("opens in the Doctor view when that was the last choice in this clinic", async () => {
    rememberWorkspace(CLINIC_A, "DOCTOR");
    render(practising);
    const view = await screen.findByRole("group", { name: "View" }, { timeout: 5000 });
    expect(within(view).getByRole("radio", { name: "Doctor" })).toBeChecked();
  });
});
