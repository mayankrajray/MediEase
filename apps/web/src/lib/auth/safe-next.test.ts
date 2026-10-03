import { describe, expect, it } from "vitest";

import { safeNextPath } from "./safe-next";

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
