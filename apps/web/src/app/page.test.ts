// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() =>
  vi.fn((path: string): never => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  }),
);
vi.mock("next/navigation", () => ({ redirect }));

import Home from "./page";

describe("home page", () => {
  it("sends everyone to Today (M6-P1; the proxy and session provider handle signed-out visitors)", () => {
    expect(() => Home()).toThrow("NEXT_REDIRECT /today");
    expect(redirect).toHaveBeenCalledWith("/today");
  });
});
