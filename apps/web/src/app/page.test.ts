// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";

const redirect = vi.hoisted(() =>
  vi.fn((path: string): never => {
    throw new Error(`NEXT_REDIRECT ${path}`);
  }),
);
const jar = vi.hoisted(() => new Map<string, string>());
vi.mock("next/navigation", () => ({ redirect }));
vi.mock("next/headers", () => ({
  cookies: () => Promise.resolve({ get: (name: string) => (jar.has(name) ? { name, value: jar.get(name) } : undefined) }),
}));

import Home, { generateMetadata } from "./page";

const search = (lang?: string) => Promise.resolve(lang === undefined ? {} : { lang });

beforeEach(() => {
  jar.clear();
  redirect.mockClear();
});

describe("home page (M6c-P8, FR-LND-01)", () => {
  it("sends signed-in staff to Today and patients to their app", async () => {
    jar.set("me_csrf", "x");
    await expect(Home({ searchParams: search() })).rejects.toThrow("NEXT_REDIRECT /today");
    jar.clear();
    jar.set("me_pt_csrf", "y");
    await expect(Home({ searchParams: search() })).rejects.toThrow("NEXT_REDIRECT /portal");
  });

  it("shows the landing page to a signed-out visitor, indexable, in Hindi when asked", async () => {
    const page = await Home({ searchParams: search("hi") });
    expect(page.props).toEqual({ language: "hi" });
    expect(redirect).not.toHaveBeenCalled();
    const meta = await generateMetadata({ searchParams: search() });
    expect(meta.robots).toEqual({ index: true, follow: true });
  });
});
