import { describe, expect, it } from "vitest";

import { visibleNav, type NavItem } from "./nav";

const items: readonly NavItem[] = [
  { href: "/queue", label: "Queue" },
  { href: "/staff", label: "Staff", requires: "STAFF_MANAGE" },
  { href: "/settings", label: "Settings", requires: "CLINIC_MANAGE" },
];

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

  it("links only to pages that exist today", () => {
    expect(visibleNav(["STAFF_MANAGE", "CLINIC_MANAGE"]).map((i) => i.href)).toEqual(["/queue"]);
    expect(visibleNav(["PATIENTS_MANAGE", "SCHEDULES_MANAGE"]).map((i) => i.href)).toEqual([
      "/queue",
      "/patients",
      "/settings/schedule",
    ]);
  });
});
