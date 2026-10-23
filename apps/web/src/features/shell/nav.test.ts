import { describe, expect, it } from "vitest";

import { visibleNav, type NavItem } from "./nav";
import { WORKSPACE_NAV } from "./workspace";

const items: readonly NavItem[] = [
  { href: "/queue", label: "Queue" },
  { href: "/staff", label: "Staff", requires: "STAFF_MANAGE" },
  { href: "/settings", label: "Settings", requires: "CLINIC_MANAGE" },
];

const OWNER = ["CLINIC_VIEW", "PATIENTS_MANAGE", "REMINDERS_SCHEDULE", "STAFF_MANAGE", "SCHEDULES_MANAGE", "CLINICAL_VIEW", "DOCTORS_VIEW"] as const;
const DOCTOR = ["CLINIC_VIEW", "PATIENTS_MANAGE", "REMINDERS_SCHEDULE", "CLINICAL_VIEW", "CLINICAL_WRITE", "DOCTORS_VIEW"] as const;
const DESK = ["CLINIC_VIEW", "PATIENTS_MANAGE", "REMINDERS_SCHEDULE", "DOCTORS_VIEW"] as const;

describe("visibleNav", () => {
  it("FR-AUTH-03: shows items with no requirement to everyone", () => {
    expect(visibleNav([], items).map((i) => i.label)).toEqual(["Queue"]);
  });

  it("FR-AUTH-03: shows an item only to roles holding its permission", () => {
    expect(visibleNav(["CLINIC_VIEW"], items).map((i) => i.label)).toEqual(["Queue"]);
    expect(visibleNav(["STAFF_MANAGE", "CLINIC_MANAGE"], items).map((i) => i.label)).toEqual([
      "Queue",
      "Staff",
      "Settings",
    ]);
  });
});

describe("each workspace's navigation (M6a-P6, decision 3A; FR-UX-04)", () => {
  it("the owner manages the clinic", () => {
    expect(visibleNav(OWNER, WORKSPACE_NAV.OWNER).map((i) => i.label)).toEqual([
      "Today",
      "Queue",
      "Patients",
      "Follow-ups",
      "Team",
      "Schedule",
      "Notifications",
    ]);
  });

  it("the doctor works on their own day and patients", () => {
    expect(visibleNav(DOCTOR, WORKSPACE_NAV.DOCTOR).map((i) => i.label)).toEqual([
      "Today",
      "My queue",
      "My patients",
      "My follow-ups",
      "My schedule",
      "Notifications",
    ]);
  });

  it("the front desk runs the day, with no clinical or admin pages", () => {
    expect(visibleNav(DESK, WORKSPACE_NAV.FRONT_DESK).map((i) => i.label)).toEqual([
      "Today",
      "Queue",
      "Patients",
      "Follow-ups",
      "Notifications",
    ]);
  });

  it("the three lists differ (FR-UX-05)", () => {
    const labels = (Object.keys(WORKSPACE_NAV) as (keyof typeof WORKSPACE_NAV)[]).map((w) =>
      WORKSPACE_NAV[w].map((i) => i.label).join("|"),
    );
    expect(new Set(labels).size).toBe(3);
  });
});
