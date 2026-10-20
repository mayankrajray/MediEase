import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiError, json, mockApi } from "@/test/api";
import { replace, resetNavigation } from "@/test/navigation";

import { CLINIC_STORAGE_KEY } from "./clinic-selection";
import { SignInForm } from "./SignInForm";
import { CLINIC_A, CLINIC_B, membership, ops, person } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const session = (access: ReturnType<typeof person>) =>
  json(200, { ...access, session: { access_expires_at: "x", refresh_expires_at: "y" } });

const oneClinic = person([membership(CLINIC_A, "Alpha Clinic")]);
const twoClinics = person([membership(CLINIC_A, "Alpha Clinic"), membership(CLINIC_B, "Beta Clinic", "DOCTOR")]);

function fill(identifier: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email or phone number"), { target: { value: identifier } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

const submit = () => fireEvent.click(screen.getByRole("button", { name: /^Sign in|Signing in/ }));

beforeEach(() => {
  resetNavigation();
});

afterEach(() => {
  vi.useRealTimers();
  window.localStorage.clear();
});

describe("SignInForm", () => {
  it("FR-AUTH-01: labels both fields and lets password managers recognise them", () => {
    render(<SignInForm next="/queue" />);

    const identifier = screen.getByLabelText("Email or phone number");
    const password = screen.getByLabelText("Password");
    expect(identifier).toHaveAttribute("autocomplete", "username");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    expect(password).toHaveAttribute("type", "password");
    expect(screen.getByRole("heading", { name: "Sign in to MediEase" })).toBeInTheDocument();
  });

  it("can show and hide the password", () => {
    render(<SignInForm next="/queue" />);
    const toggle = screen.getByRole("button", { name: "Show password" });

    fireEvent.click(toggle);
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
    expect(toggle).toHaveAccessibleName("Hide password");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it("FR-AUTH-01: posts the trimmed identifier and the password, then opens the queue", async () => {
    const api = mockApi({ "POST /api/v1/auth/sign-in": () => session(oneClinic) });
    render(<SignInForm next="/queue" />);

    fill("  owner@sample-clinic.example ", "a-synthetic-password");
    submit();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue"));
    expect(api.calls[0]?.body).toEqual({
      identifier: "owner@sample-clinic.example",
      password: "a-synthetic-password",
    });
  });

  it("keeps the person on the button while the page changes: no second request, no flash of the form", async () => {
    const api = mockApi({ "POST /api/v1/auth/sign-in": () => session(oneClinic) });
    render(<SignInForm next="/queue" />);

    fill("owner@sample-clinic.example", "a-synthetic-password");
    submit();
    await waitFor(() => expect(replace).toHaveBeenCalled());

    expect(screen.getByRole("button", { name: "Signing in…" })).toBeDisabled();
    expect(api.count("POST /api/v1/auth/sign-in")).toBe(1);
  });

  it("sends one request when submitted twice quickly", async () => {
    const api = mockApi({ "POST /api/v1/auth/sign-in": () => session(oneClinic) });
    render(<SignInForm next="/queue" />);
    fill("owner@sample-clinic.example", "a-synthetic-password");

    fireEvent.submit(screen.getByRole("button", { name: "Sign in" }).closest("form") as HTMLFormElement);
    fireEvent.submit(screen.getByRole("button", { name: /Sign/ }).closest("form") as HTMLFormElement);

    await waitFor(() => expect(replace).toHaveBeenCalledTimes(1));
    expect(api.count("POST /api/v1/auth/sign-in")).toBe(1);
  });

  it("FR-AUTH-03: a multi-clinic person with no remembered clinic goes to the chooser", async () => {
    mockApi({ "POST /api/v1/auth/sign-in": () => session(twoClinics) });
    render(<SignInForm next="/today" />);

    fill("doctor@sample-clinic.example", "a-synthetic-password");
    submit();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/select-clinic"));
  });

  it("FR-AUTH-03: with a remembered clinic they go straight to where they were headed", async () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, CLINIC_B);
    mockApi({ "POST /api/v1/auth/sign-in": () => session(twoClinics) });
    render(<SignInForm next="/queue?day=today" />);

    fill("doctor@sample-clinic.example", "a-synthetic-password");
    submit();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue?day=today"));
  });

  it("R10: an ops user goes to the ops console", async () => {
    mockApi({ "POST /api/v1/auth/sign-in": () => session(ops()) });
    render(<SignInForm next="/queue" />);

    fill("ops@mediease.example", "a-synthetic-password");
    submit();

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/ops"));
  });

  it("R2: a wrong password shows the API's message and Ref, clears the password, keeps the identifier and refocuses the password", async () => {
    mockApi({
      "POST /api/v1/auth/sign-in": () =>
        apiError(401, "AUTH_INVALID_CREDENTIALS", "Wrong login details. Check them and try again."),
    });
    render(<SignInForm next="/queue" />);

    fill("owner@sample-clinic.example", "wrong-password");
    submit();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Wrong login details. Check them and try again.");
    expect(alert).toHaveTextContent("Ref: test-ref");
    expect(screen.getByLabelText("Email or phone number")).toHaveValue("owner@sample-clinic.example");
    const password = screen.getByLabelText("Password");
    expect(password).toHaveValue("");
    await act(async () => {}); // the focus moves in an effect after the alert renders
    expect(password).toHaveFocus();
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAccessibleDescription(/Wrong login details/);
    expect(replace).not.toHaveBeenCalled();
    // The button is usable again.
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("FR-AUTH-04: a locked account says how long to wait, disables the button, and re-enables it when the wait is over", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    mockApi({
      "POST /api/v1/auth/sign-in": () =>
        apiError(423, "AUTH_LOCKED", "Account temporarily locked", { "Retry-After": "840" }),
    });
    render(<SignInForm next="/queue" />);

    fill("owner@sample-clinic.example", "a-synthetic-password");
    submit();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Too many attempts. Try again in 14 minutes.");
    expect(alert).toHaveTextContent("Ref: test-ref");
    await act(async () => {}); // the focus moves in an effect after the alert renders
    expect(alert).toHaveFocus();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();

    await act(async () => {
      vi.advanceTimersByTime(840_000);
    });
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });

  it("an unreachable API keeps what was typed and offers Try again, which signs in", async () => {
    let up = false;
    const api = mockApi({
      "POST /api/v1/auth/sign-in": () => {
        if (!up) throw new TypeError("fetch failed");
        return session(oneClinic);
      },
    });
    render(<SignInForm next="/queue" />);

    fill("owner@sample-clinic.example", "a-synthetic-password");
    submit();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The API could not be reached.");
    expect(screen.getByLabelText("Password")).toHaveValue("a-synthetic-password");

    up = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue"));
    expect(api.count("POST /api/v1/auth/sign-in")).toBe(2);
  });

  it("a validation error shows the API's message without clearing the password", async () => {
    mockApi({
      "POST /api/v1/auth/sign-in": () => apiError(422, "REQ_VALIDATION_FAILED", "Check the highlighted fields."),
    });
    render(<SignInForm next="/queue" />);

    fill("owner@sample-clinic.example", "a-synthetic-password");
    submit();

    expect(await screen.findByRole("alert")).toHaveTextContent("Check the highlighted fields.");
    expect(screen.getByLabelText("Password")).toHaveValue("a-synthetic-password");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it.each([
    ["session_ended", "Your session ended. Please sign in again."],
    ["session_ended_for_safety", "Your session was ended for safety."],
    ["account_disabled", "This account has been deactivated. Contact your clinic owner."],
  ] as const)("R5, R7: explains why the person is here (%s)", (reason, text) => {
    render(<SignInForm next="/queue" reason={reason} />);

    expect(screen.getByRole("status")).toHaveTextContent(text);
  });

  it("shows no reason when there is none", () => {
    render(<SignInForm next="/queue" />);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
