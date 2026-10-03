import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiError, json, mockApi, noContent } from "@/test/api";
import { resetRefreshState } from "@/lib/auth/refresh";
import { replace, resetNavigation } from "@/test/navigation";

import { CLINIC_STORAGE_KEY } from "./clinic-selection";
import { SessionProvider, useSession } from "./SessionProvider";
import { CLINIC_A, CLINIC_B, membership, person } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const twoClinics = person([membership(CLINIC_A, "Alpha Clinic"), membership(CLINIC_B, "Beta Clinic", "DOCTOR")]);
const oneClinic = person([membership(CLINIC_A, "Alpha Clinic")]);

function Probe() {
  const session = useSession();
  return (
    <div>
      <p>name: {session.identity.user.full_name}</p>
      <p>clinic: {session.clinic.kind === "active" ? session.clinic.membership.clinic_name : session.clinic.kind}</p>
      <button type="button" onClick={() => session.selectClinic(CLINIC_B)}>
        pick beta
      </button>
      <button type="button" onClick={() => session.selectClinic("not-a-clinic-of-mine")}>
        pick unknown
      </button>
      <button type="button" onClick={() => void session.signOut()}>
        sign out
      </button>
    </div>
  );
}

const expired = () => apiError(401, "AUTH_SESSION_EXPIRED", "Please sign in again");

function renderProvider() {
  return render(
    <SessionProvider>
      <Probe />
    </SessionProvider>,
  );
}

function setCsrfCookie(present: boolean) {
  document.cookie = present
    ? "me_csrf=csrf-token; path=/"
    : "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  window.history.replaceState(null, "", "/queue");
  setCsrfCookie(true);
});

afterEach(() => {
  setCsrfCookie(false);
  window.localStorage.clear();
});

describe("SessionProvider", () => {
  it("FR-AUTH-03: shows a loading state, then the children with the identity", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, oneClinic) });

    renderProvider();

    expect(screen.getByRole("status")).toHaveTextContent("Loading your session");
    expect(await screen.findByText("name: Sample Person")).toBeInTheDocument();
    expect(screen.getByText("clinic: Alpha Clinic")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("FR-AUTH-02: an expired access token is refreshed silently and the page carries on", async () => {
    const api = mockApi({
      "GET /api/v1/me": [expired, expired, () => json(200, oneClinic)],
      "POST /api/v1/auth/refresh": () => json(200, { ...oneClinic, session: {} }),
    });

    renderProvider();

    expect(await screen.findByText("name: Sample Person")).toBeInTheDocument();
    expect(api.count("POST /api/v1/auth/refresh")).toBe(1);
    expect(replace).not.toHaveBeenCalled();
  });

  it("R5: a session that cannot be refreshed sends the person to sign in, remembering where they were", async () => {
    window.history.replaceState(null, "", "/queue?day=today");
    mockApi({
      "GET /api/v1/me": expired,
      "POST /api/v1/auth/refresh": expired,
    });

    renderProvider();

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fqueue%3Fday%3Dtoday&reason=session_ended"),
    );
  });

  it("a visitor who was never signed in is not told their session ended", async () => {
    setCsrfCookie(false);
    mockApi({ "GET /api/v1/me": expired, "POST /api/v1/auth/refresh": expired });

    renderProvider();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fqueue"));
  });

  it("R5: a reused refresh token ends the session with the safety message", async () => {
    mockApi({
      "GET /api/v1/me": expired,
      "POST /api/v1/auth/refresh": () => apiError(401, "AUTH_REFRESH_REUSED", "Session ended for safety"),
    });

    renderProvider();

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fqueue&reason=session_ended_for_safety"),
    );
  });

  it("R7, AC4: a deactivated account is sent to sign in with the deactivated message", async () => {
    mockApi({ "GET /api/v1/me": () => apiError(403, "AUTH_ACCOUNT_DISABLED", "Account disabled") });

    renderProvider();

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/sign-in?next=%2Fqueue&reason=account_disabled"),
    );
  });

  it("an unreachable API shows the message, a Ref and Try again, and recovers on retry", async () => {
    let up = false;
    mockApi({
      "GET /api/v1/me": () => {
        if (!up) throw new TypeError("fetch failed");
        return json(200, oneClinic);
      },
    });

    renderProvider();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The API could not be reached.");
    expect(alert).toHaveTextContent("Ref:");
    expect(replace).not.toHaveBeenCalled();

    up = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("name: Sample Person")).toBeInTheDocument();
  });

  it("FR-AUTH-03: a multi-clinic user with no remembered clinic must choose", async () => {
    mockApi({ "GET /api/v1/me": () => json(200, twoClinics) });

    renderProvider();

    expect(await screen.findByText("clinic: choose")).toBeInTheDocument();
  });

  it("FR-AUTH-03: the remembered clinic is used on load, and choosing one remembers it", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    mockApi({ "GET /api/v1/me": () => json(200, twoClinics) });

    renderProvider();

    expect(await screen.findByText("clinic: Alpha Clinic")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "pick beta" }));
    expect(screen.getByText("clinic: Beta Clinic")).toBeInTheDocument();
    expect(window.localStorage.getItem(CLINIC_STORAGE_KEY)).toBe(CLINIC_B);
  });

  it("ignores a choice that is not one of the person's clinics", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    mockApi({ "GET /api/v1/me": () => json(200, twoClinics) });

    renderProvider();
    await screen.findByText("clinic: Alpha Clinic");
    fireEvent.click(screen.getByRole("button", { name: "pick unknown" }));

    expect(screen.getByText("clinic: Alpha Clinic")).toBeInTheDocument();
    expect(window.localStorage.getItem(CLINIC_STORAGE_KEY)).toBe(CLINIC_A);
  });

  it("FR-AUTH-01: sign-out calls the API with the CSRF header, forgets the clinic and leaves", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    const api = mockApi({
      "GET /api/v1/me": () => json(200, twoClinics),
      "POST /api/v1/auth/sign-out": () => noContent(),
    });

    renderProvider();
    await screen.findByText("name: Sample Person");
    fireEvent.click(screen.getByRole("button", { name: "sign out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sign-in"));
    const call = api.calls.find((c) => c.path === "/api/v1/auth/sign-out");
    expect(call?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(window.localStorage.getItem(CLINIC_STORAGE_KEY)).toBeNull();
  });

  it("sign-out still leaves, and forgets the clinic, when the API cannot be reached", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_A);
    mockApi({
      "GET /api/v1/me": () => json(200, twoClinics),
      "POST /api/v1/auth/sign-out": () => {
        throw new TypeError("fetch failed");
      },
    });

    renderProvider();
    await screen.findByText("name: Sample Person");
    fireEvent.click(screen.getByRole("button", { name: "sign out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sign-in"));
    expect(window.localStorage.getItem(CLINIC_STORAGE_KEY)).toBeNull();
  });
});
