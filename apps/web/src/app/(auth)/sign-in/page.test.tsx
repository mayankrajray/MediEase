import { isValidElement } from "react";
import { describe, expect, it, vi } from "vitest";

import SignInPage from "./page";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

async function propsFor(query: Record<string, string | string[] | undefined>) {
  const element = await SignInPage({ searchParams: Promise.resolve(query) });
  if (!isValidElement<{ next: string; reason?: string }>(element)) {
    throw new Error("expected a React element");
  }
  return element.props;
}

describe("sign-in page (?next= and ?reason= come from the URL)", () => {
  it("passes a same-site next path and an allow-listed reason to the form", async () => {
    expect(await propsFor({ next: "/queue?day=today", reason: "session_ended" })).toEqual({
      next: "/queue?day=today",
      reason: "session_ended",
    });
  });

  it("defaults next to the queue and omits an absent reason", async () => {
    expect(await propsFor({})).toEqual({ next: "/queue" });
  });

  it.each(["https://evil.example", "//evil.example", "javascript:alert(1)", "/\\evil.example"])(
    "replaces the open-redirect attempt %j with the queue",
    async (next) => {
      expect((await propsFor({ next })).next).toBe("/queue");
    },
  );

  it("drops an unknown reason instead of showing attacker-chosen text", async () => {
    expect(await propsFor({ reason: "<b>Call 555-0100</b>" })).toEqual({ next: "/queue" });
  });

  it("uses the first value when a parameter is repeated", async () => {
    expect((await propsFor({ next: ["/queue", "https://evil.example"] })).next).toBe("/queue");
  });
});
