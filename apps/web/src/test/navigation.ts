/** Test helper: a stand-in for `next/navigation` that records navigation. */

import { vi } from "vitest";

export const replace = vi.fn<(href: string) => void>();
export const push = vi.fn<(href: string) => void>();
export const navigation = { pathname: "/queue", search: "" };

// One router object for the whole run: Next's useRouter() is stable across renders,
// and effects that list it as a dependency must not re-run on every render.
const router = { replace, push, refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() };

/** Use as: vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock) */
export const nextNavigationMock = {
  useRouter: () => router,
  usePathname: () => navigation.pathname,
  // A new object per call is fine: callers read it, they do not list it as a dependency.
  useSearchParams: () => new URLSearchParams(navigation.search),
  redirect: vi.fn(),
};

export function resetNavigation(): void {
  replace.mockReset();
  push.mockReset();
  navigation.pathname = "/queue";
  navigation.search = "";
}
