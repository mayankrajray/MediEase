import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiError, json, mockApi } from "@/test/api";
import { replace, resetNavigation } from "@/test/navigation";

import { AcceptInviteForm } from "./AcceptInviteForm";
import { CLINIC_A, membership, person } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const DESCRIBE = "GET /api/v1/auth/invites/tok-123";
const ACCEPT = "POST /api/v1/auth/invites/tok-123/accept";

const invite = (overrides: Record<string, unknown> = {}) =>
  json(200, {
    clinic_name: "Alpha Clinic",
    full_name: "Sample Desk",
    role: "FRONT_DESK",
    expires_at: null,
    has_password: false,
    ...overrides,
  });

const joined = () =>
  json(200, {
    ...person([membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK")]),
    session: { access_expires_at: "x", refresh_expires_at: "y" },
  });

const PASSWORD = "a-long-synthetic-password";

function fill(password: string, confirmation: string) {
  fireEvent.change(screen.getByLabelText("Choose a password"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("Type it again"), { target: { value: confirmation } });
}

beforeEach(() => {
  resetNavigation();
});

describe("AcceptInviteForm", () => {
  it("FR-ORG-04: says which clinic and role the invitation is for", async () => {
    mockApi({ [DESCRIBE]: () => invite() });

    render(<AcceptInviteForm token="tok-123" />);

    expect(screen.getByRole("status")).toHaveTextContent("Checking your invitation");
    expect(await screen.findByRole("heading", { name: "Join Alpha Clinic" })).toBeInTheDocument();
    expect(screen.getByText(/Sample Desk, you have been invited as/)).toHaveTextContent("Front desk");
  });

  it("FR-ORG-04: sets the password, joins and lands on the queue signed in", async () => {
    const api = mockApi({ [DESCRIBE]: () => invite(), [ACCEPT]: () => joined() });
    render(<AcceptInviteForm token="tok-123" />);
    await screen.findByLabelText("Choose a password");

    fill(PASSWORD, PASSWORD);
    fireEvent.click(screen.getByRole("button", { name: "Set password and join" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue"));
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ password: PASSWORD });
  });

  it("does not send anything when the two passwords differ", async () => {
    const api = mockApi({ [DESCRIBE]: () => invite(), [ACCEPT]: () => joined() });
    render(<AcceptInviteForm token="tok-123" />);
    await screen.findByLabelText("Choose a password");

    fill(PASSWORD, `${PASSWORD}x`);
    fireEvent.click(screen.getByRole("button", { name: "Set password and join" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The two passwords are not the same.");
    expect(api.count(ACCEPT)).toBe(0);
    expect(screen.getByLabelText("Type it again")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows the API's message when the password is refused, and lets the person retry", async () => {
    mockApi({
      [DESCRIBE]: () => invite(),
      [ACCEPT]: () =>
        apiError(422, "REQ_VALIDATION_FAILED", "The password must be at least 12 characters."),
    });
    render(<AcceptInviteForm token="tok-123" />);
    await screen.findByLabelText("Choose a password");

    fill("short", "short");
    fireEvent.click(screen.getByRole("button", { name: "Set password and join" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The password must be at least 12 characters.");
    expect(alert).toHaveTextContent("Ref: test-ref");
    expect(screen.getByRole("button", { name: "Set password and join" })).toBeEnabled();
    expect(replace).not.toHaveBeenCalled();
  });

  it.each([
    [404, "CLN_INVITE_INVALID", "This invitation link is not valid."],
    [410, "CLN_INVITE_EXPIRED", "This invitation has expired."],
    [410, "CLN_INVITE_USED", "This invitation has already been used."],
  ])("an unusable invitation (%s %s) says so and points to sign in", async (status, code, message) => {
    mockApi({ [DESCRIBE]: () => apiError(status, code, message) });

    render(<AcceptInviteForm token="tok-123" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("link", { name: "sign in" })).toHaveAttribute("href", "/sign-in");
    expect(screen.queryByLabelText("Choose a password")).not.toBeInTheDocument();
  });

  it("an unreachable API offers Try again, which loads the invitation", async () => {
    let up = false;
    mockApi({
      [DESCRIBE]: () => {
        if (!up) throw new TypeError("fetch failed");
        return invite();
      },
    });
    render(<AcceptInviteForm token="tok-123" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The API could not be reached.");

    up = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Join Alpha Clinic" })).toBeInTheDocument();
  });

  it("R13: an invitation for an existing account asks for its current password, not a new one", async () => {
    const api = mockApi({
      [DESCRIBE]: () => invite({ has_password: true }),
      [ACCEPT]: () => joined(),
    });
    render(<AcceptInviteForm token="tok-123" />);

    const field = await screen.findByLabelText("Your MediEase password");
    expect(field).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByText(/you keep your password/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Choose a password")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Type it again")).not.toBeInTheDocument();

    fireEvent.change(field, { target: { value: PASSWORD } });
    fireEvent.click(screen.getByRole("button", { name: "Join" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/queue"));
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ password: PASSWORD });
  });

  it("R13: a wrong current password shows the API's message, clears the field and refocuses it", async () => {
    mockApi({
      [DESCRIBE]: () => invite({ has_password: true }),
      [ACCEPT]: () =>
        apiError(401, "AUTH_INVALID_CREDENTIALS", "Wrong login details. Check them and try again."),
    });
    render(<AcceptInviteForm token="tok-123" />);
    const field = await screen.findByLabelText("Your MediEase password");

    fireEvent.change(field, { target: { value: "not-my-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Join" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Wrong login details");
    expect(alert).toHaveTextContent("Ref: test-ref");
    expect(field).toHaveValue("");
    expect(field).toHaveFocus();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(replace).not.toHaveBeenCalled();
  });

  it("R13, FR-AUTH-04: a locked account says how long to wait", async () => {
    mockApi({
      [DESCRIBE]: () => invite({ has_password: true }),
      [ACCEPT]: () =>
        apiError(423, "AUTH_LOCKED", "Account temporarily locked", { "Retry-After": "840" }),
    });
    render(<AcceptInviteForm token="tok-123" />);
    const field = await screen.findByLabelText("Your MediEase password");

    fireEvent.change(field, { target: { value: PASSWORD } });
    fireEvent.click(screen.getByRole("button", { name: "Join" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Too many attempts. Try again in 14 minutes.",
    );
  });
  it("URL-encodes the token it was given", async () => {
    const api = mockApi({ "GET /api/v1/auth/invites/a%2Fb": () => invite() });

    render(<AcceptInviteForm token="a/b" />);

    await screen.findByRole("heading", { name: "Join Alpha Clinic" });
    expect(api.calls[0]?.path).toBe("/api/v1/auth/invites/a%2Fb");
  });
});
