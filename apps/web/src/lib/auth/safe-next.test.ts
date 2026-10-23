import { describe, expect, it } from "vitest";

import { isPortalPath, safeNextPath, safePortalNextPath, safeStaffNextPath } from "./safe-next";

describe("safeNextPath (open-redirect guard)", () => {
  it.each(["/queue", "/queue?tab=1", "/select-clinic#top", "/a/b/c"])("keeps %s", (path) => {
    expect(safeNextPath(path, "/fallback")).toBe(path);
  });

  it.each([
    ["nothing", undefined],
    ["null", null],
    ["empty", ""],
    ["relative", "queue"],
    ["protocol-relative", "//evil.example"],
    ["absolute", "https://evil.example/queue"],
    ["javascript scheme", "javascript:alert(1)"],
    ["backslash", "/\\evil.example"],
    ["tab (stripped by URL parsers)", "/\t/evil.example"],
    ["newline", "/\n/evil.example"],
    ["NUL", "/queue\u0000"],
    ["the sign-in page itself", "/sign-in?next=/queue"],
  ])("rejects %s", (_label, raw) => {
    expect(safeNextPath(raw, "/fallback")).toBe("/fallback");
  });

  it("defaults the fallback to the home page", () => {
    expect(safeNextPath("https://evil.example")).toBe("/");
  });

  it("returns a normalised path on this site", () => {
    expect(safeNextPath("/a/../queue")).toBe("/queue");
  });
});

describe("portal and staff landings (M6a-P3, ADR-0015)", () => {
  it.each(["/portal", "/portal/appointments?x=1"])("a patient may land on %s", (path) => {
    expect(safePortalNextPath(path)).toBe(path);
  });

  it.each(["/today", "/queue", "/portal/sign-in", "/portal/sign-up?next=/portal", "/portalx", "//evil.example"])(
    "a patient never lands on %s",
    (path) => {
      expect(safePortalNextPath(path)).toBe("/portal");
    },
  );

  it("staff never land in the portal", () => {
    expect(safeStaffNextPath("/portal", "/today")).toBe("/today");
    expect(safeStaffNextPath("/portal/x", "/today")).toBe("/today");
    expect(safeStaffNextPath("/queue", "/today")).toBe("/queue");
  });

  it("no sign-in page is ever a landing", () => {
    expect(safeNextPath("/portal/sign-in", "/f")).toBe("/f");
    expect(isPortalPath("/portal")).toBe(true);
    expect(isPortalPath("/portalx")).toBe(false);
  });
});
