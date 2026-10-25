import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { ops } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { ApplicationsWaiting } from "./ApplicationsWaiting";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const item = (overrides: Record<string, unknown> = {}) => ({
  id: "0192f0a0-0000-7000-8000-0000000000c1",
  reference: "MA-2026-0042",
  kind: "SOLO_DOCTOR",
  clinic_name: "Sample Applying Clinic",
  city: "Pune",
  doctors: 1,
  submitted_at: "2026-10-26T05:00:00+00:00",
  email_verified_at: "2026-10-26T05:10:00+00:00",
  possible_duplicate: false,
  ...overrides,
});

function renderIt() {
  return render(
    <SessionProvider>
      <ApplicationsWaiting />
    </SessionProvider>,
  );
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => vi.unstubAllGlobals());

describe("applications waiting (M6c-P1, clinic-onboarding R18)", () => {
  it("counts the confirmed applications and lists them, flagging a possible duplicate", async () => {
    mockApi({
      "GET /api/v1/me": () => json(200, ops()),
      "GET /api/v1/ops/applications": () =>
        json(200, { items: [item(), item({ id: "0192f0a0-0000-7000-8000-0000000000c2", reference: "MA-2026-0043", kind: "CLINIC", doctors: 3, possible_duplicate: true })] }),
    });
    renderIt();
    expect(await screen.findByRole("heading", { name: "2 applications waiting" })).toBeInTheDocument();
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent(/MA-2026-0042.*Sample Applying Clinic, Pune.*Own practice.*1/);
    expect(rows[1]).toHaveTextContent(/MA-2026-0043.*Possible duplicate.*Clinic.*3/);
  });

  it("says when none is waiting", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, ops()), "GET /api/v1/ops/applications": () => json(200, { items: [] }) });
    renderIt();
    expect(await screen.findByRole("heading", { name: "No applications waiting" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
