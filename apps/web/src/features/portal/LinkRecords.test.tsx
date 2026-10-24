import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { navigation, replace, resetNavigation } from "@/test/navigation";

import { AcceptInvite, LinkFromPrescription } from "./LinkRecords";
import { me, renderPortal } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const TOKEN = "secret-invite-token";
const INVITE = `/api/v1/portal/invites/${TOKEN}`;
const DESCRIBED = { clinic_name: "Sample Clinic", patient_first_name: "Asha", patient_code: "SC-0004" };
const LINKED = {
  id: "0192f0a0-0000-7000-8000-0000000000e1",
  clinic_id: "0192f0a0-0000-7000-8000-0000000000e2",
  clinic_name: "Sample Clinic",
  patient_first_name: "Asha",
  patient_code: "SC-0004",
  method: "INVITE",
  linked_at: "2026-10-24T05:30:00Z",
};

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  navigation.pathname = "/portal/link/x";
  document.cookie = "me_pt_csrf=portal-csrf; path=/";
});

afterEach(() => {
  document.cookie = "me_pt_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("AcceptInvite (M6b-P1, FR-PRT-06 b)", () => {
  it("AC1: shows whose records the invite is for and links them on confirm", async () => {
    const api = mockApi({
      ...me(),
      [`GET ${INVITE}`]: () => json(200, DESCRIBED),
      [`POST ${INVITE}/accept`]: () => json(201, LINKED),
    });
    await renderPortal(<AcceptInvite token={TOKEN} />);

    expect(await screen.findByRole("heading", { name: "Link your records at Sample Clinic" })).toBeInTheDocument();
    expect(screen.getByText(/^Asha ·/)).toHaveTextContent("Asha · SC-0004");
    fireEvent.click(screen.getByRole("button", { name: "Link" }));

    expect(await screen.findByRole("heading", { name: "Linked" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Sample Clinic (Asha · SC-0004)");
    expect(api.calls.find((c) => c.method === "POST")?.headers.get("X-CSRF-Token")).toBe("portal-csrf");
  });

  it("R2: a used, replaced or expired invite says it is no longer valid", async () => {
    mockApi({ ...me(), [`GET ${INVITE}`]: () => apiError(404, "PRT_INVITE_INVALID", "This invitation is no longer valid.") });
    await renderPortal(<AcceptInvite token={TOKEN} />);
    expect(await screen.findByRole("heading", { name: "This invitation is no longer valid" })).toBeInTheDocument();
  });

  it("Not me leaves without linking", async () => {
    const api = mockApi({ ...me(), [`GET ${INVITE}`]: () => json(200, DESCRIBED) });
    await renderPortal(<AcceptInvite token={TOKEN} />);
    fireEvent.click(await screen.findByRole("button", { name: "Not me" }));
    expect(replace).toHaveBeenCalledWith("/portal");
    expect(api.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("R4: an account already linked in the clinic is told in the portal's words", async () => {
    mockApi({
      ...me(),
      [`GET ${INVITE}`]: () => json(200, DESCRIBED),
      [`POST ${INVITE}/accept`]: () => apiError(409, "PRT_ALREADY_LINKED", "These records can't be linked to this account."),
    });
    await renderPortal(<AcceptInvite token={TOKEN} />);
    fireEvent.click(await screen.findByRole("button", { name: "Link" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Contact the clinic");
  });

  it("M6b-P2: in Hindi when the account is", async () => {
    mockApi({ ...me({ language: "hi" }), [`GET ${INVITE}`]: () => json(200, DESCRIBED) });
    await renderPortal(<AcceptInvite token={TOKEN} />);
    expect(await screen.findByRole("heading", { name: "Sample Clinic के अपने रिकॉर्ड जोड़ें" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "जोड़ें" })).toBeInTheDocument();
  });

  it("an ended session goes back to the portal sign-in, then here", async () => {
    mockApi({ ...me(), [`GET ${INVITE}`]: () => apiError(401, "AUTH_REFRESH_REUSED", "Ended for safety.") });
    await renderPortal(<AcceptInvite token={TOKEN} />);
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/portal/sign-in?reason=session_ended_for_safety&next=%2Fportal%2Flink%2Fx"),
    );
  });
});

describe("LinkFromPrescription (M6b-P1, FR-PRT-06 c)", () => {
  it("R5: an unverified account is asked to confirm its email first, before any check", async () => {
    const api = mockApi(me({ email_verified: false }));
    await renderPortal(<LinkFromPrescription token="rx-token" />);
    expect(await screen.findByRole("heading", { name: "Confirm your email first" })).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("R6: a wrong answer says how many tries are left; the right one links", async () => {
    const api = mockApi({
      ...me(),
      "POST /api/v1/portal/links/prescription": [
        () => apiError(401, "LINK_CHALLENGE_FAILED", "Those digits don't match.", {}, { attempts_left: "4" }),
        () => json(201, { ...LINKED, method: "RX_LINK" }),
      ],
    });
    await renderPortal(<LinkFromPrescription token="rx-token" />);
    const field = await screen.findByLabelText("Last 4 digits of your phone number");
    fireEvent.change(field, { target: { value: "0000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to my MediEase" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("4 tries left");

    fireEvent.change(field, { target: { value: "0101" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to my MediEase" }));
    expect(await screen.findByRole("heading", { name: "Linked" })).toBeInTheDocument();
    const posts = api.calls.filter((c) => c.method === "POST");
    expect(posts.map((c) => c.body)).toEqual([
      { token: "rx-token", phone_last4: "0000" },
      { token: "rx-token", phone_last4: "0101" },
    ]);
  });

  it("R6: a locked link says so", async () => {
    mockApi({
      ...me(),
      "POST /api/v1/portal/links/prescription": () => apiError(423, "LINK_LOCKED", "Too many attempts. Please contact the clinic."),
    });
    await renderPortal(<LinkFromPrescription token="rx-token" />);
    fireEvent.change(await screen.findByLabelText("Last 4 digits of your phone number"), { target: { value: "0101" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to my MediEase" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });
});