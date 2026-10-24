import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotPasswordForm } from "@/features/auth/ForgotPasswordForm";
import { ResetPasswordForm } from "@/features/auth/ResetPasswordForm";
import { forgotWords, resetWords } from "@/lib/i18n/portal";
import { json, mockApi, noContent } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { VerifyEmail } from "./VerifyEmail";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

beforeEach(() => {
  resetNavigation();
});

function field(id: string): HTMLElement {
  const found = document.getElementById(id);
  if (found === null) throw new Error(`no #${id}`);
  return found;
}

describe("the emailed-link pages in Hindi (M6b-P2, spec R21)", () => {
  it("forgot password asks and confirms in Hindi", async () => {
    mockApi({ "POST /api/v1/portal/auth/password-reset": () => json(202, { accepted: true }) });
    render(<ForgotPasswordForm kind="patient" signInHref="/portal/sign-in" words={forgotWords("hi")} />);
    expect(screen.getByRole("heading", { name: "अपना पासवर्ड बदलें" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/ईमेल/), { target: { value: "asha.patient@example.test" } });
    fireEvent.click(screen.getByRole("button", { name: "लिंक भेजें" }));
    expect(await screen.findByRole("status")).toHaveTextContent("30 मिनट");
    expect(screen.getByRole("link", { name: "साइन इन पर वापस जाएँ" })).toHaveAttribute("href", "/portal/sign-in");
  });

  it("reset password checks the length and match in Hindi", () => {
    const api = mockApi({});
    render(
      <ResetPasswordForm
        kind="patient"
        token="t"
        signInPath="/portal/sign-in"
        forgotPath="/portal/forgot-password"
        words={resetWords("hi")}
      />,
    );
    expect(screen.getByRole("heading", { name: "नया पासवर्ड चुनें" })).toBeInTheDocument();
    fireEvent.change(field("new-password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "नया पासवर्ड सहेजें" }));
    expect(screen.getByText("कम से कम 12 अक्षर लिखें।")).toBeInTheDocument();
    fireEvent.change(field("new-password"), { target: { value: "a-long-enough-pass" } });
    fireEvent.change(field("confirm-password"), { target: { value: "something-else-here" } });
    fireEvent.click(screen.getByRole("button", { name: "नया पासवर्ड सहेजें" }));
    expect(screen.getByText("दोनों पासवर्ड एक जैसे नहीं हैं।")).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it("verify email confirms in Hindi", async () => {
    mockApi({ "POST /api/v1/portal/auth/verify-email": () => noContent() });
    render(<VerifyEmail token="t" language="hi" />);
    fireEvent.click(screen.getByRole("button", { name: "मेरे ईमेल की पुष्टि करें" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("पुष्टि हो गई"));
  });

  it("staff and an English portal keep the English words", () => {
    render(<ForgotPasswordForm kind="staff" signInHref="/sign-in" />);
    expect(screen.getByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send the link" })).toBeInTheDocument();
  });
});
