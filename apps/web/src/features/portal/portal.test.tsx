import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { replace, resetNavigation } from "@/test/navigation";

import { PortalSignInForm } from "./PortalSignInForm";
import { PortalSignUpForm } from "./PortalSignUpForm";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const ACCOUNT = {
  id: "0199a000-0000-7000-8000-000000000001",
  full_name: "Asha Patient",
  email: "asha.patient@example.test",
  sign_in_method: "PASSWORD",
  email_verified: false,
  language: "en",
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
      language: "en",
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

describe("the sign-in pages in Hindi (M6b-P2, spec R21)", () => {
  it("sign-up says it in Hindi and creates a Hindi account", async () => {
    const api = mockApi({ "POST /api/v1/portal/auth/sign-up": () => json(201, { account: { ...ACCOUNT, language: "hi" } }) });
    render(<PortalSignUpForm next="/portal" language="hi" />);
    expect(screen.getByRole("heading", { name: "अपना हेल्थ खाता बनाएँ" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/आपका नाम/), { target: { value: "Asha Patient" } });
    fireEvent.change(screen.getByLabelText(/ईमेल/), { target: { value: "asha.patient@example.test" } });
    fireEvent.change(screen.getByLabelText(/^पासवर्ड/), { target: { value: "a-long-enough-pass" } });
    fireEvent.click(screen.getByRole("button", { name: "खाता बनाएँ" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/portal"));
    expect(api.calls[0]?.body).toMatchObject({ language: "hi" });
  });

  it("sign-in is in Hindi", () => {
    render(<PortalSignInForm next="/portal" language="hi" />);
    expect(screen.getByRole("heading", { name: "अपने हेल्थ खाते में साइन इन करें" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "खाता बनाएँ" })).toHaveAttribute("href", "/portal/sign-up?next=%2Fportal");
  });
});