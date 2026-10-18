import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_STORAGE_KEY } from "@/features/auth/clinic-selection";
import type { Membership } from "@/features/auth/landing";
import { SessionProvider } from "@/features/auth/SessionProvider";
import { CLINIC_A, CLINIC_B, membership, ops, person } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi, noContent, type Recorded } from "@/test/api";
import { navigation, replace, resetNavigation } from "@/test/navigation";

import { EmptyQueue } from "./EmptyQueue";
import { WorkspaceGuard } from "./WorkspaceGuard";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const alpha = membership(CLINIC_A, "Alpha Clinic", "OWNER");
const beta = membership(CLINIC_B, "Beta Clinic", "DOCTOR");

const CLINICS: Record<string, { id: string; name: string; timezone: string }> = {
  [CLINIC_A]: { id: CLINIC_A, name: "Alpha Clinic", timezone: "Asia/Kolkata" },
  [CLINIC_B]: { id: CLINIC_B, name: "Beta Clinic", timezone: "Asia/Dubai" },
};

/** GET /clinic answers for the clinic named in X-Clinic-ID, or the only one when none is named. */
function clinicRoute(only: string = CLINIC_A) {
  return (call: Recorded) => {
    const id = call.headers.get("X-Clinic-ID") ?? only;
    return json(200, { ...CLINICS[id], slug: "x", status: "ACTIVE", specialties: [] });
  };
}

function renderWorkspace() {
  return render(
    <SessionProvider>
      <WorkspaceGuard>
        <EmptyQueue />
      </WorkspaceGuard>
    </SessionProvider>,
  );
}

function withMemberships(...memberships: Membership[]) {
  return person(memberships);
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  window.history.replaceState(null, "", "/queue");
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

describe("dashboard shell", () => {
  it("FR-AUTH-03: shows the clinic, the role and the empty queue, with no switcher and no clinic header for a one-clinic person", async () => {
    const api = mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(alpha)),
      "GET /api/v1/clinic": clinicRoute(),
    });

    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Today's queue" })).toBeInTheDocument();
    const header = screen.getByRole("banner");
    expect(within(header).getByText("Alpha Clinic")).toBeInTheDocument();
    expect(within(header).getByText("Owner")).toBeInTheDocument();
    expect(within(header).getByText("Sample Person")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Clinic" })).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing here yet/)).toBeInTheDocument();
    expect(screen.getByText("Asia/Kolkata")).toBeInTheDocument(); // the clinic's own time zone
    expect(screen.getByRole("link", { name: "Queue" })).toHaveAttribute("aria-current", "page");
    expect(api.calls.find((c) => c.path === "/api/v1/clinic")?.headers.has("X-Clinic-ID")).toBe(false);
  });

  it("marks only the section being shown as current (M4-P6 fix)", async () => {
    const owner = membership(CLINIC_A, "Alpha Clinic", "OWNER", {
      permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "SCHEDULES_MANAGE"],
    });
    mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(owner)),
      "GET /api/v1/clinic": clinicRoute(),
    });
    navigation.pathname = "/patients/0192f0a0-0000-7000-8000-0000000000c1";

    renderWorkspace();

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Patients" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Queue" })).not.toHaveAttribute("aria-current");
    expect(within(nav).getByRole("link", { name: "Schedule" })).not.toHaveAttribute("aria-current");
  });

  it("shows the person's name and role but never their email or phone", async () => {
    mockApi({
      "GET /api/v1/me": () =>
        json(200, {
          ...withMemberships(alpha),
          user: { id: "u", full_name: "Sample Person", email: "p@sample-clinic.example", phone_e164: "+919000000001", is_platform_ops: false },
        }),
      "GET /api/v1/clinic": clinicRoute(),
    });

    renderWorkspace();
    await screen.findByRole("heading", { name: "Today's queue" });

    expect(document.body).not.toHaveTextContent("p@sample-clinic.example");
    expect(document.body).not.toHaveTextContent("+919000000001");
  });

  it("test_fr_auth_03_switcher_only_for_multiple_memberships: a two-clinic person gets the switcher and X-Clinic-ID", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    const api = mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(alpha, beta)),
      "GET /api/v1/clinic": clinicRoute(),
    });

    renderWorkspace();

    expect(await screen.findByRole("combobox", { name: "Clinic" })).toHaveValue(CLINIC_A);
    await screen.findByText("Asia/Kolkata");
    expect(api.calls.find((c) => c.path === "/api/v1/clinic")?.headers.get("X-Clinic-ID")).toBe(CLINIC_A);
  });

  it("FR-AUTH-03, R6: switching clinic loads the other clinic with its own header and remembers the choice", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    const api = mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(alpha, beta)),
      "GET /api/v1/clinic": clinicRoute(),
    });
    renderWorkspace();
    await screen.findByText("Asia/Kolkata");

    fireEvent.change(screen.getByRole("combobox", { name: "Clinic" }), { target: { value: CLINIC_B } });

    expect(await screen.findByText("Asia/Dubai")).toBeInTheDocument();
    expect(screen.queryByText("Asia/Kolkata")).not.toBeInTheDocument(); // nothing of clinic A is left
    const headers = api.calls.filter((c) => c.path === "/api/v1/clinic").map((c) => c.headers.get("X-Clinic-ID"));
    expect(headers).toEqual([CLINIC_A, CLINIC_B]);
    expect(within(screen.getByRole("banner")).getByText("Doctor")).toBeInTheDocument();
    expect(window.localStorage.getItem(CLINIC_STORAGE_KEY)).toBe(CLINIC_B);
  });

  it("R6: several clinics and nothing remembered sends the person to the chooser, keeping where they were", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, withMemberships(alpha, beta)) });

    renderWorkspace();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/select-clinic?next=%2Fqueue"));
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
  });

  it("R6: a remembered clinic that the API no longer accepts is forgotten and the person chooses again", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(alpha, beta)),
      "GET /api/v1/clinic": () => apiError(400, "PERM_CLINIC_REQUIRED", "Choose a clinic"),
    });

    renderWorkspace();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/select-clinic?next=%2Fqueue"));
    expect(window.localStorage.getItem(CLINIC_STORAGE_KEY)).toBeNull();
  });

  it("R10: an ops user is sent to the ops console, not the clinic workspace", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, ops()) });

    renderWorkspace();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/ops"));
    expect(screen.queryByRole("heading", { name: "Today's queue" })).not.toBeInTheDocument();
  });

  it("FR-ORG-04: a person with no clinic is told so and can sign out", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, withMemberships()) });

    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "No clinic access yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("I1: a clinic still being set up says so, and the shell works", async () => {
    mockApi({
      "GET /api/v1/me": () => json(200, withMemberships({ ...alpha, clinic_status: "ONBOARDING" })),
      "GET /api/v1/clinic": clinicRoute(),
    });

    renderWorkspace();

    expect(await screen.findByText("Setup for this clinic is still in progress.")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Today's queue" })).toBeInTheDocument();
  });

  it("CLN_SUSPENDED: a suspended clinic shows the API's message and Ref, and the switcher still works", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    mockApi({
      "GET /api/v1/me": () => json(200, withMemberships({ ...alpha, clinic_status: "SUSPENDED" }, beta)),
      "GET /api/v1/clinic": (call) =>
        call.headers.get("X-Clinic-ID") === CLINIC_A
          ? apiError(403, "CLN_SUSPENDED", "This clinic is suspended.")
          : json(200, { ...CLINICS[CLINIC_B], slug: "b", status: "ACTIVE", specialties: [] }),
    });

    renderWorkspace();

    expect(await screen.findByRole("heading", { name: "Alpha Clinic is suspended" })).toBeInTheDocument();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("This clinic is suspended.");
    expect(alert).toHaveTextContent("Ref: test-ref");

    fireEvent.change(screen.getByRole("combobox", { name: "Clinic" }), { target: { value: CLINIC_B } });
    expect(await screen.findByText("Asia/Dubai")).toBeInTheDocument();
  });

  it("an unreachable API shows Try again, which loads the clinic", async () => {
    let up = false;
    mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(alpha)),
      "GET /api/v1/clinic": (call) => {
        if (!up) throw new TypeError("fetch failed");
        return clinicRoute()(call);
      },
    });
    renderWorkspace();
    expect(await screen.findByRole("alert")).toHaveTextContent("The API could not be reached.");

    up = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Today's queue" })).toBeInTheDocument();
  });

  it("R7, AC4: a session that ends while the clinic loads sends the person to sign in", async () => {
    mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(alpha)),
      "GET /api/v1/clinic": () => apiError(403, "AUTH_ACCOUNT_DISABLED", "Account disabled"),
    });

    renderWorkspace();

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fqueue&reason=account_disabled"),
    );
  });

  it("FR-AUTH-01: Sign out in the header ends the session and leaves", async () => {
    const api = mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(alpha)),
      "GET /api/v1/clinic": clinicRoute(),
      "POST /api/v1/auth/sign-out": () => noContent(),
    });
    renderWorkspace();
    await screen.findByRole("heading", { name: "Today's queue" });

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sign-in"));
    expect(api.count("POST /api/v1/auth/sign-out")).toBe(1);
  });

  it("offers a skip link and landmarks for keyboard and screen-reader users", async () => {
    mockApi({
      "GET /api/v1/me": () => json(200, withMemberships(alpha)),
      "GET /api/v1/clinic": clinicRoute(),
    });

    renderWorkspace();
    await screen.findByRole("heading", { name: "Today's queue" });

    expect(screen.getByRole("link", { name: "Skip to content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
  });
});
