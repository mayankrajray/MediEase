import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import type { StaffMember, TeamInvitation } from "./api";
import { TeamPage } from "./TeamPage";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const owner = membership(CLINIC_A, "Alpha Clinic", "OWNER", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "CLINIC_MANAGE", "STAFF_MANAGE"],
});
const ME = owner.membership_id;
const DESK = "0192f0a0-0000-7000-8000-0000000005d1";
const INVITED = "0192f0a0-0000-7000-8000-0000000005d2";
const GONE = "0192f0a0-0000-7000-8000-0000000005d3";

function member(overrides: Partial<StaffMember> = {}): StaffMember {
  return {
    membership_id: DESK,
    user_id: "0192f0a0-0000-7000-8000-0000000005e1",
    full_name: "Asha Desk",
    role: "FRONT_DESK",
    status: "ACTIVE",
    email: "asha@sample-clinic.example",
    phone_e164: null,
    invite_expires_at: null,
    has_doctor_profile: false,
    ...overrides,
  };
}

const team = (): StaffMember[] => [
  member({ membership_id: GONE, full_name: "Old Helper", status: "DEACTIVATED", phone_e164: "+919000000301", email: null }),
  member({
    membership_id: INVITED,
    full_name: "Bala Invited",
    status: "INVITED",
    role: "DOCTOR",
    email: "bala@sample-clinic.example",
    invite_expires_at: "2026-10-30T06:30:00+00:00",
  }),
  member(),
  member({ membership_id: ME, full_name: "Sample Person", role: "OWNER", has_doctor_profile: true }),
];

function invitation(overrides: Partial<TeamInvitation> = {}): TeamInvitation {
  return {
    ...member({ membership_id: "0192f0a0-0000-7000-8000-0000000005d9", full_name: "New Doc", status: "INVITED", role: "DOCTOR" }),
    delivery: "email",
    email_masked: "n***@sample-clinic.example",
    accept_url: null,
    ...overrides,
  };
}

const routes = {
  ...workspaceRoutes,
  "GET /api/v1/me": () => json(200, person([owner])),
  "GET /api/v1/clinic/staff": () => json(200, { items: team() }),
};

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

const heading = () => screen.findByRole("heading", { level: 1, name: "Team" }, { timeout: 5000 });
const row = (name: RegExp) => screen.findByRole("row", { name }, { timeout: 5000 });

describe("the owner's Team page (M6a-P5, FR-ORG-07)", () => {
  it("lists active, then invited, then deactivated members with their role, status and contact", async () => {
    mockApi(routes);
    renderInWorkspace(<TeamPage />);
    await heading();

    await row(/Asha Desk/);
    const names = screen.getAllByRole("rowheader").map((cell) => cell.textContent);
    expect(names).toEqual(["Asha Desk", "Sample Person (you)", "Bala Invited", "Old Helper"]);
    const invited = screen.getByRole("row", { name: /Bala Invited/ });
    expect(invited).toHaveTextContent("Invited");
    expect(invited).toHaveTextContent("Link expires 30 Oct 2026, 12:00 IST");
    expect(invited).toHaveTextContent("bala@sample-clinic.example");
    expect(screen.getByRole("row", { name: /Sample Person/ })).toHaveTextContent("Doctor profile");
    expect(screen.getByRole("row", { name: /Old Helper/ })).toHaveTextContent("+919000000301");
  });

  it("hides Deactivate on your own row and offers Invite back only for a deactivated member", async () => {
    mockApi(routes);
    renderInWorkspace(<TeamPage />);
    await heading();

    const mine = await row(/Sample Person/);
    expect(within(mine).queryByRole("button", { name: /Deactivate/ })).not.toBeInTheDocument();
    expect(within(mine).getByRole("button", { name: "Change role of Sample Person" })).toBeInTheDocument();
    const gone = screen.getByRole("row", { name: /Old Helper/ });
    expect(within(gone).getAllByRole("button").map((b) => b.textContent)).toEqual(["Invite back Old Helper"]);
    const invited = screen.getByRole("row", { name: /Bala Invited/ });
    expect(within(invited).getByRole("button", { name: "Resend invitation to Bala Invited" })).toBeInTheDocument();
  });

  it("an emailed invitation says where it went and adds the row, showing no link", async () => {
    const api = mockApi({ ...routes, "POST /api/v1/clinic/staff": () => json(201, invitation()) });
    renderInWorkspace(<TeamPage />);
    await heading();

    fireEvent.click(screen.getByRole("button", { name: "Invite someone" }));
    const drawer = await screen.findByRole("dialog", { name: "Invite someone" });
    fireEvent.change(within(drawer).getByLabelText(/Full name/), { target: { value: "New Doc" } });
    fireEvent.change(within(drawer).getByLabelText("Role"), { target: { value: "DOCTOR" } });
    fireEvent.change(within(drawer).getByLabelText("Email"), { target: { value: "new@sample-clinic.example" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Send invitation" }));

    expect(await screen.findByText("Invitation emailed to n***@sample-clinic.example.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await row(/New Doc/)).toHaveTextContent("Sending the email…");
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
      full_name: "New Doc",
      role: "DOCTOR",
      email: "new@sample-clinic.example",
      phone: null,
    });
  });

  it("a phone-only invitation shows its link once, to copy", async () => {
    mockApi({
      ...routes,
      "POST /api/v1/clinic/staff": () =>
        json(
          201,
          invitation({ email: null, phone_e164: "+919000000302", delivery: "link", email_masked: null, accept_url: "http://localhost:3000/invite/secret-1" }),
        ),
    });
    renderInWorkspace(<TeamPage />);
    await heading();

    fireEvent.click(screen.getByRole("button", { name: "Invite someone" }));
    const drawer = await screen.findByRole("dialog", { name: "Invite someone" });
    fireEvent.change(within(drawer).getByLabelText(/Full name/), { target: { value: "New Doc" } });
    fireEvent.change(within(drawer).getByLabelText("Phone"), { target: { value: "9000000302" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Send invitation" }));

    expect(await within(drawer).findByLabelText("Invitation link for New Doc")).toHaveValue("http://localhost:3000/invite/secret-1");
    expect(within(drawer).getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  });

  it("asks for an email or a phone before sending", async () => {
    const api = mockApi(routes);
    renderInWorkspace(<TeamPage />);
    await heading();

    fireEvent.click(screen.getByRole("button", { name: "Invite someone" }));
    const drawer = await screen.findByRole("dialog", { name: "Invite someone" });
    fireEvent.change(within(drawer).getByLabelText(/Full name/), { target: { value: "New Doc" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Send invitation" }));

    expect(await within(drawer).findByText(/Enter an email address or a phone number/)).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("Resend says the invitation was emailed again", async () => {
    const api = mockApi({
      ...routes,
      [`POST /api/v1/clinic/staff/${INVITED}/resend`]: () =>
        json(200, invitation({ membership_id: INVITED, full_name: "Bala Invited", email_masked: "b***@sample-clinic.example" })),
    });
    renderInWorkspace(<TeamPage />);
    await heading();

    fireEvent.click(await screen.findByRole("button", { name: "Resend invitation to Bala Invited" }, { timeout: 5000 }));

    expect(await screen.findByText("Invitation emailed to b***@sample-clinic.example.")).toBeInTheDocument();
    expect(api.calls.some((c) => c.path === `/api/v1/clinic/staff/${INVITED}/resend`)).toBe(true);
  });

  it("changes a role in a dialog and updates the row", async () => {
    const api = mockApi({
      ...routes,
      [`PATCH /api/v1/clinic/staff/${DESK}`]: () => json(200, member({ role: "DOCTOR" })),
    });
    renderInWorkspace(<TeamPage />);
    await heading();

    fireEvent.click(await screen.findByRole("button", { name: "Change role of Asha Desk" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog", { name: "Change Asha Desk's role" });
    const save = within(dialog).getByRole("button", { name: "Save role" });
    expect(save).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("radio", { name: /Doctor/ }));
    fireEvent.click(save);

    expect(await screen.findByText("Asha Desk is now Doctor.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ role: "DOCTOR" });
    expect(screen.getByRole("row", { name: /Asha Desk/ })).toHaveTextContent("Doctor");
  });

  it("shows the last-owner refusal as the API words it, and warns before demoting yourself", async () => {
    mockApi({
      ...routes,
      [`PATCH /api/v1/clinic/staff/${ME}`]: () => apiError(409, "CLN_LAST_OWNER", "A clinic needs at least one owner."),
    });
    renderInWorkspace(<TeamPage />);
    await heading();

    fireEvent.click(await screen.findByRole("button", { name: "Change role of Sample Person" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog", { name: "Change Sample Person's role" });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Front desk/ }));
    expect(within(dialog).getByText(/You will lose this Team page/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save role" }));

    const alert = await within(dialog).findByRole("alert");
    expect(alert).toHaveTextContent("A clinic needs at least one owner.");
    expect(alert).toHaveTextContent("Ref: test-ref");
  });

  it("demoting yourself leaves for Today", async () => {
    const leave = vi.fn();
    mockApi({
      ...routes,
      [`PATCH /api/v1/clinic/staff/${ME}`]: () =>
        json(200, member({ membership_id: ME, full_name: "Sample Person", role: "DOCTOR" })),
    });
    renderInWorkspace(<TeamPage onSelfDemoted={leave} />);
    await heading();

    fireEvent.click(await screen.findByRole("button", { name: "Change role of Sample Person" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog", { name: "Change Sample Person's role" });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Doctor/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save role" }));

    await waitFor(() => expect(leave).toHaveBeenCalledOnce());
  });

  it("deactivates behind a confirmation that says what happens", async () => {
    const api = mockApi({
      ...routes,
      [`PATCH /api/v1/clinic/staff/${DESK}`]: () => json(200, member({ status: "DEACTIVATED" })),
    });
    renderInWorkspace(<TeamPage />);
    await heading();

    fireEvent.click(await screen.findByRole("button", { name: "Deactivate Asha Desk" }, { timeout: 5000 }));
    const dialog = await screen.findByRole("dialog", { name: "Deactivate Asha Desk?" });
    expect(dialog).toHaveTextContent("signed out of this clinic on their next click");
    fireEvent.click(within(dialog).getByRole("button", { name: "Deactivate" }));

    expect(await screen.findByText("Asha Desk is deactivated.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ status: "DEACTIVATED" });
    expect(screen.getByRole("row", { name: /Asha Desk/ })).toHaveTextContent("Deactivated");
  });

  it("Invite back fills in the person and says they keep their history", async () => {
    const api = mockApi({
      ...routes,
      "POST /api/v1/clinic/staff": () =>
        json(201, invitation({ membership_id: GONE, full_name: "Old Helper", email: null, phone_e164: "+919000000301", delivery: "link", email_masked: null, accept_url: "http://localhost:3000/invite/secret-2" })),
    });
    renderInWorkspace(<TeamPage />);
    await heading();

    fireEvent.click(await screen.findByRole("button", { name: "Invite back Old Helper" }, { timeout: 5000 }));
    const drawer = await screen.findByRole("dialog", { name: "Invite Old Helper back" });
    expect(drawer).toHaveTextContent("They keep their account and their history");
    expect(within(drawer).getByLabelText("Phone")).toHaveValue("+919000000301");
    fireEvent.click(within(drawer).getByRole("button", { name: "Send invitation" }));

    expect(await within(drawer).findByLabelText("Invitation link for Old Helper")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
      full_name: "Old Helper",
      role: "FRONT_DESK",
      email: null,
      phone: "+919000000301",
    });
  });

  it("a failed load shows the Ref and Try again", async () => {
    mockApi({
      ...routes,
      "GET /api/v1/clinic/staff": [() => apiError(503, "SYS_UNAVAILABLE", "Try again shortly."), () => json(200, { items: team() })],
    });
    renderInWorkspace(<TeamPage />);
    await heading();

    expect(await screen.findByRole("alert", undefined, { timeout: 5000 })).toHaveTextContent("Ref: test-ref");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await row(/Asha Desk/)).toBeInTheDocument();
  });
});
