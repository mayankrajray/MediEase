import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi, noContent } from "@/test/api";
import { replace, resetNavigation } from "@/test/navigation";

import { PortalAccount } from "./PortalAccount";
import { PortalSignInForm } from "./PortalSignInForm";
import { PortalSignUpForm } from "./PortalSignUpForm";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const ACCOUNT = {
  id: "0199a000-0000-7000-8000-000000000001",
  full_name: "Asha Patient",
  email: "asha.patient@example.test",
  sign_in_method: "PASSWORD",
  email_verified: false,
} as const;
const SESSION = { account: ACCOUNT, session: { access_expires_at: "x", refresh_expires_at: "y" } };

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_pt_csrf=portal-csrf; path=/";
  document.cookie = "me_csrf=staff-csrf; path=/";
});

describe("PortalSignUpForm (M6a-P3, FR-PRT-01)", () => {
  function fill(name: string, email: string, password: string) {
    fireEvent.change(screen.getByLabelText(/Your name/), { target: { value: name } });
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: email } });
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: password } });
  }

  it("FR-PRT-01: creates the account and opens the portal", async () => {
    const api = mockApi({ "POST /api/v1/portal/auth/sign-up": () => json(201, SESSION) });
    render(<PortalSignUpForm next="/portal" />);
    fill(" Asha Patient ", " asha.patient@example.test ", "a-long-synthetic-pass");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/portal"));
    expect(api.calls[0]?.body).toEqual({
      full_name: "Asha Patient",
      email: "asha.patient@example.test",
      password: "a-long-synthetic-pass",
    });
  });

  it("FR-AUTH-01: asks for 12 characters before sending anything", () => {
    const api = mockApi({});
    render(<PortalSignUpForm next="/portal" />);
    fill("Asha", "a@example.test", "short");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByText("Use at least 12 characters.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Password/)).toHaveAttribute("aria-invalid", "true");
    expect(api.calls).toHaveLength(0);
  });

  it("ADR-0015: says when the email already has an account, with the Ref", async () => {
    mockApi({
      "POST /api/v1/portal/auth/sign-up": () =>
        apiError(409, "PRT_EMAIL_TAKEN", "An account with this email already exists. Sign in instead."),
    });
    render(<PortalSignUpForm next="/portal" />);
    fill("Asha", "a@example.test", "a-long-synthetic-pass");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("already exists");
    expect(alert).toHaveTextContent("Ref: test-ref");
    expect(replace).not.toHaveBeenCalled();
  });

  it("offers Google for patients", () => {
    render(<PortalSignUpForm next="/portal" />);
    expect(screen.getByRole("link", { name: /Continue with Google/ })).toHaveAttribute(
      "href",
      "/api/v1/auth/google/start?intent=patient&next=%2Fportal",
    );
  });
});

describe("PortalSignInForm (M6a-P3)", () => {
  it("signs in with email and password and opens next", async () => {
    const api = mockApi({ "POST /api/v1/portal/auth/sign-in": () => json(200, SESSION) });
    render(<PortalSignInForm next="/portal" />);
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "asha.patient@example.test" } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "a-long-synthetic-pass" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/portal"));
    expect(api.calls[0]?.body).toEqual({ email: "asha.patient@example.test", password: "a-long-synthetic-pass" });
  });

  it("shows the generic error and clears the password", async () => {
    mockApi({
      "POST /api/v1/portal/auth/sign-in": () =>
        apiError(401, "PRT_INVALID_CREDENTIALS", "The email or password is incorrect."),
    });
    render(<PortalSignInForm next="/portal" />);
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "asha.patient@example.test" } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The email or password is incorrect.");
    expect(screen.getByLabelText(/Password/)).toHaveValue("");
  });

  it("explains why the person is here, from an allow-listed reason only", () => {
    render(<PortalSignInForm next="/portal" reason="google_failed" />);
    expect(screen.getByRole("status")).toHaveTextContent("Google sign-in did not work");
  });
});

describe("PortalAccount (M6a-P3, decision 8)", () => {
  it("FR-PRT-01: shows the account, how it signs in, and that no clinic is linked", async () => {
    mockApi({ "GET /api/v1/portal/me": () => json(200, { account: ACCOUNT }) });
    render(<PortalAccount />);

    expect(await screen.findByRole("heading", { name: "Hello, Asha Patient" })).toBeInTheDocument();
    expect(screen.getByText("Email and password")).toBeInTheDocument();
    expect(screen.getByText("Not verified yet")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "No clinic linked yet" })).toBeInTheDocument();
  });

  it("ADR-0015: signs out with the portal's CSRF key, not the staff one", async () => {
    const api = mockApi({
      "GET /api/v1/portal/me": () => json(200, { account: { ...ACCOUNT, sign_in_method: "GOOGLE" } }),
      "POST /api/v1/portal/auth/sign-out": () => noContent(),
    });
    render(<PortalAccount />);
    expect(await screen.findByText("Google")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/portal/sign-in"));
    const signOut = api.calls.find((c) => c.path === "/api/v1/portal/auth/sign-out");
    expect(signOut?.headers.get("X-CSRF-Token")).toBe("portal-csrf");
  });

  it("refreshes an expired portal session once, then shows the account", async () => {
    const api = mockApi({
      "GET /api/v1/portal/me": [
        () => apiError(401, "AUTH_SESSION_EXPIRED", "Your session has ended."),
        () => apiError(401, "AUTH_SESSION_EXPIRED", "Your session has ended."),
        () => json(200, { account: ACCOUNT }),
      ],
      "POST /api/v1/portal/auth/refresh": () => json(200, SESSION),
    });
    render(<PortalAccount />);

    expect(await screen.findByRole("heading", { name: "Hello, Asha Patient" })).toBeInTheDocument();
    expect(api.count("POST /api/v1/portal/auth/refresh")).toBe(1);
    expect(api.calls.find((c) => c.path.endsWith("/refresh"))?.headers.get("X-CSRF-Token")).toBe("portal-csrf");
  });

  it("sends an ended session back to the portal sign-in with a reason", async () => {
    mockApi({
      "GET /api/v1/portal/me": () => apiError(401, "AUTH_REFRESH_REUSED", "Ended for safety."),
    });
    render(<PortalAccount />);
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/portal/sign-in?reason=session_ended_for_safety"),
    );
  });

  it("shows a failure with the Ref and Try again", async () => {
    mockApi({ "GET /api/v1/portal/me": () => apiError(500, "SYS_UNEXPECTED", "An unexpected error occurred.") });
    render(<PortalAccount />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Ref: test-ref");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
