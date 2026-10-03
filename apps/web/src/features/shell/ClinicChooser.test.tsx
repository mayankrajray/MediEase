import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_STORAGE_KEY } from "@/features/auth/clinic-selection";
import { SessionProvider } from "@/features/auth/SessionProvider";
import { CLINIC_A, CLINIC_B, membership, ops, person } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi } from "@/test/api";
import { replace, resetNavigation } from "@/test/navigation";

import { ClinicChooser } from "./ClinicChooser";
import { OpsShell } from "./OpsShell";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const alpha = membership(CLINIC_A, "Alpha Clinic", "OWNER");
const beta = membership(CLINIC_B, "Beta Clinic", "DOCTOR", { clinic_status: "ONBOARDING" });

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

describe("ClinicChooser", () => {
  const renderChooser = (next = "/queue") =>
    render(
      <SessionProvider>
        <ClinicChooser next={next} />
      </SessionProvider>,
    );

  it("FR-AUTH-03: lists each clinic with the role and any status, and choosing one remembers it and moves on", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, person([alpha, beta])) });
    renderChooser("/queue?day=today");

    expect(await screen.findByRole("heading", { name: "Choose a clinic" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Alpha Clinic/ })).toHaveTextContent("Owner");
    expect(screen.getByRole("button", { name: /Beta Clinic/ })).toHaveTextContent("Doctor · Setup in progress");

    fireEvent.click(screen.getByRole("button", { name: /Beta Clinic/ }));

    expect(window.localStorage.getItem(CLINIC_STORAGE_KEY)).toBe(CLINIC_B);
    expect(replace).toHaveBeenCalledWith("/queue?day=today");
  });

  it("marks the clinic currently in use", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    mockApi({ "GET /api/v1/me": () => json(200, person([alpha, beta])) });
    renderChooser();

    const current = await screen.findByRole("button", { name: /Alpha Clinic/ });

    expect(current).toHaveTextContent("· current");
    expect(current).toHaveAttribute("aria-current", "true");
  });

  it("a person with one clinic has nothing to choose: they go to the queue", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, person([alpha])) });

    renderChooser();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue"));
    expect(screen.queryByRole("heading", { name: "Choose a clinic" })).not.toBeInTheDocument();
  });

  it("R10: an ops user is sent to the ops console", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, ops()) });

    renderChooser();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/ops"));
  });
});

describe("OpsShell", () => {
  const renderOps = () =>
    render(
      <SessionProvider>
        <OpsShell>
          <p>console page</p>
        </OpsShell>
      </SessionProvider>,
    );

  it("R10: frames the console for platform staff", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, ops()) });

    renderOps();

    expect(await screen.findByText("console page")).toBeInTheDocument();
    expect(screen.getByText("Ops console")).toBeInTheDocument();
    expect(screen.getByText("Sample Ops")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("R10: clinic staff are sent to their queue and never see the console", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, person([alpha])) });

    renderOps();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue"));
    expect(screen.queryByText("console page")).not.toBeInTheDocument();
  });
});
