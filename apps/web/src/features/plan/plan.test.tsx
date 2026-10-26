import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi } from "@/test/api";

import { PlanPage } from "./PlanPage";
import { trialText, type Subscription } from "./api";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const owner = membership(CLINIC_A, "Alpha Clinic", "OWNER", {
  permissions: ["CLINIC_VIEW", "CLINIC_MANAGE", "STAFF_MANAGE"],
});

function subscription(overrides: Partial<Subscription> = {}): Subscription {
  return {
    plan: "SOLO",
    plan_name: "Solo",
    trial_state: "ACTIVE",
    trial_ends_at: "2026-11-09T05:00:00+00:00",
    trial_days_left: 14,
    trial_started_at: "2026-10-26T05:00:00+00:00",
    limits: { doctors: 1, users: 2 },
    usage: { doctors: 1, users: 2 },
    ...overrides,
  };
}

const routes = (s: Subscription) => ({
  ...workspaceRoutes,
  "GET /api/v1/me": () => json(200, person([owner])),
  "GET /api/v1/clinic/subscription": () => json(200, s),
});

beforeEach(() => resetRefreshState());
afterEach(() => vi.unstubAllGlobals());

describe("plan and trial (M6d-P7, FR-SUB-01)", () => {
  it("R6: the owner sees the plan, what is used of it and the trial's days left", async () => {
    mockApi(routes(subscription()));
    renderInWorkspace(<PlanPage />);
    expect(await screen.findByText("1 of 1")).toBeInTheDocument();
    expect(screen.getByText("2 of 2")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Plan" })).toBeInTheDocument();
    expect(screen.getByText(/Free trial: 14 days left/)).toBeInTheDocument();
    expect(screen.getByText(/contact MediEase/)).toBeInTheDocument();
  });

  it("R2: no limit on people is said in words", async () => {
    mockApi(
      routes(
        subscription({
          plan: "PLUS",
          plan_name: "Clinic Plus",
          trial_state: "NONE",
          trial_ends_at: null,
          trial_days_left: null,
          limits: { doctors: 5, users: null },
          usage: { doctors: 2, users: 7 },
        }),
      ),
    );
    renderInWorkspace(<PlanPage />);
    expect(await screen.findByText("7 (no limit)")).toBeInTheDocument();
    expect(screen.queryByText(/Free trial/)).not.toBeInTheDocument();
  });

  it("D5: an ended trial is a notice for the owner on every page, and locks nothing", async () => {
    mockApi(routes(subscription({ trial_state: "ENDED", trial_days_left: 0 })));
    renderInWorkspace(<p>Page content</p>);
    expect(await screen.findByText(/Your free trial has ended/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See your plan" })).toHaveAttribute("href", "/settings/plan");
    expect(screen.getByText("Page content")).toBeInTheDocument();
  });

  it("trial words", () => {
    expect(trialText(subscription({ trial_days_left: 1 }))).toBe("Free trial: 1 day left");
    expect(trialText(subscription({ trial_state: "NOT_STARTED" }))).toBe("Free trial starts when the clinic goes live");
    expect(trialText(subscription({ trial_state: "NONE" }))).toBeUndefined();
  });
});
