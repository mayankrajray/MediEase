import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VerifyEmail } from "@/features/portal/VerifyEmail";
import { apiError, json, mockApi, noContent } from "@/test/api";
import { replace, resetNavigation } from "@/test/navigation";

import { ForgotPasswordForm } from "./ForgotPasswordForm";
import { ResetPasswordForm } from "./ResetPasswordForm";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

beforeEach(() => {
  resetNavigation();
});

describe("ForgotPasswordForm (M6a-P4, FR-AUTH-05)", () => {
  it.each([
    ["staff", "/api/v1/auth/password-reset"],
    ["patient", "/api/v1/portal/auth/password-reset"],
  ] as const)("FR-AUTH-05: %s asks for a link and is told the same thing either way", async (kind, path) => {
    const api = mockApi({ [`POST ${path}`]: () => json(202, { accepted: true }) });
    render(<ForgotPasswordForm kind={kind} signInHref="/sign-in" />);
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: " asha@example.test " } });
    fireEvent.click(screen.getByRole("button", { name: "Send the link" }));

    expect(await screen.findByRole("status")).toHaveTextContent("If an account uses that email");
    expect(api.calls[0]?.body).toEqual({ email: "asha@example.test" });
  });

  it("shows a rate limit with the Ref", async () => {
    mockApi({
      "POST /api/v1/auth/password-reset": () =>
        apiError(429, "AUTH_RATE_LIMITED", "Too many attempts. Wait a minute and try again.", {
          "Retry-After": "30",
        }),
    });
    render(<ForgotPasswordForm kind="staff" signInHref="/sign-in" />);
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: "a@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Send the link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ref: test-ref");
  });
});

describe("ResetPasswordForm (M6a-P4, ADR-0016 decision 7)", () => {
  function fill(password: string, confirm = password) {
    fireEvent.change(screen.getByLabelText(/^New password/), { target: { value: password } });
    fireEvent.change(screen.getByLabelText(/Type it again/), { target: { value: confirm } });
    fireEvent.click(screen.getByRole("button", { name: "Save the new password" }));
  }

  it("FR-AUTH-05: saves the new password with the link's token, then returns to sign-in", async () => {
    const api = mockApi({ "POST /api/v1/portal/auth/password-reset/complete": () => noContent() });
    render(
      <ResetPasswordForm kind="patient" token="tok-1" signInPath="/portal/sign-in" forgotPath="/portal/forgot-password" />,
    );
    fill("a-brand-new-synthetic-pass");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/portal/sign-in?reason=password_reset"));
    expect(api.calls[0]?.body).toEqual({ token: "tok-1", password: "a-brand-new-synthetic-pass" });
  });

  it("checks length and a matching confirmation before sending", () => {
    const api = mockApi({});
    render(<ResetPasswordForm kind="staff" token="t" signInPath="/sign-in" forgotPath="/forgot-password" />);
    fill("short");
    expect(screen.getByText("Use at least 12 characters.")).toBeInTheDocument();
    fill("a-brand-new-synthetic-pass", "something-else-entirely");
    expect(screen.getByText("The two passwords are not the same.")).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it("a used or expired link offers a new one", async () => {
    mockApi({
      "POST /api/v1/auth/password-reset/complete": () =>
        apiError(410, "AUTH_TOKEN_EXPIRED", "This link has expired. Ask for a new one."),
    });
    render(<ResetPasswordForm kind="staff" token="t" signInPath="/sign-in" forgotPath="/forgot-password" />);
    fill("a-brand-new-synthetic-pass");
    expect(await screen.findByRole("alert")).toHaveTextContent("This link has expired");
    expect(screen.getByRole("link", { name: "Ask for a new link" })).toHaveAttribute("href", "/forgot-password");
    expect(screen.queryByRole("button", { name: "Save the new password" })).not.toBeInTheDocument();
  });
});

describe("VerifyEmail (M6a-P4, FR-AUTH-08)", () => {
  it("ADR-0016 decision 6: opening the page sends nothing; the button confirms", async () => {
    const api = mockApi({ "POST /api/v1/portal/auth/verify-email": () => noContent() });
    render(<VerifyEmail token="tok-v" />);
    expect(api.calls).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Confirm my email" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Your email is confirmed");
    expect(api.calls[0]?.body).toEqual({ token: "tok-v" });
  });

  it("shows why a stale link failed", async () => {
    mockApi({
      "POST /api/v1/portal/auth/verify-email": () =>
        apiError(404, "AUTH_TOKEN_INVALID", "This link is not valid any more. Ask for a new one."),
    });
    render(<VerifyEmail token="old" />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm my email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not valid any more");
  });
});
