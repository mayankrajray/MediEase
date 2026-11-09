import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PortalSignUpForm } from "@/features/portal/PortalSignUpForm";
import { mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { ForgotPasswordForm } from "./ForgotPasswordForm";
import { ResetPasswordForm } from "./ResetPasswordForm";
import { SignInForm } from "./SignInForm";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

beforeEach(() => resetNavigation());

/** M7c-P7 (M2; DESIGN.md §8a): the sign-in and password forms check fields as the person goes. */
describe("authentication forms (M7c-P7, M2)", () => {
  it("sign-in: an empty submit says what is missing under each field, focuses the first, sends nothing", () => {
    const api = mockApi({});
    render(<SignInForm next="/today" />);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter your email or phone number.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email or phone number")).toHaveFocus();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
    expect(api.calls).toHaveLength(0);
  });

  it("sign-in: the password can be shown and hidden, named in words", () => {
    mockApi({});
    render(<SignInForm next="/today" />);
    const toggle = screen.getByRole("button", { name: "Show password" });
    fireEvent.click(toggle);
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
  });

  it("forgot password: the email is checked when the person leaves the field", () => {
    const api = mockApi({});
    render(<ForgotPasswordForm kind="staff" signInHref="/sign-in" />);
    const email = screen.getByLabelText(/^Email/);
    fireEvent.change(email, { target: { value: "asha@" } });
    fireEvent.blur(email);
    expect(screen.getByText("Enter an email address like name@example.com.")).toBeInTheDocument();
    fireEvent.change(email, { target: { value: "asha@example.test" } });
    expect(screen.queryByText("Enter an email address like name@example.com.")).toBeNull();
    expect(api.calls).toHaveLength(0);
  });

  it("reset: the rules tick off as typed and the mismatch sits on the second field", () => {
    mockApi({});
    render(<ResetPasswordForm kind="staff" token="t" signInPath="/sign-in" forgotPath="/forgot-password" />);
    const rules = () => screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(rules()).toEqual(["✓12 or more characters: not yet", "✓Both entries match: not yet"]);
    fireEvent.change(screen.getByLabelText(/^New password/), { target: { value: "a-long-synthetic-pass" } });
    fireEvent.change(screen.getByLabelText(/^Type it again/), { target: { value: "a-long-synthetic-pazz" } });
    expect(rules()[0]).toContain("done");
    fireEvent.click(screen.getByRole("button", { name: "Save the new password" }));
    const confirm = screen.getByLabelText(/^Type it again/);
    expect(confirm).toHaveAttribute("aria-invalid", "true");
    expect(confirm).toHaveAccessibleDescription(/The two passwords are not the same/);
    expect(confirm).toHaveFocus();
  });

  it("sign-up: the name shows its character count and the first problem takes focus", () => {
    const api = mockApi({});
    render(<PortalSignUpForm next="/portal" />);
    fireEvent.change(screen.getByLabelText(/^Your name/), { target: { value: "Asha Rao" } });
    expect(screen.getByText("8 of 200")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByLabelText(/^Email/)).toHaveFocus();
    expect(screen.getByText("Enter your email address.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Your name/)).toHaveValue("Asha Rao");
    expect(api.calls).toHaveLength(0);
  });
});
