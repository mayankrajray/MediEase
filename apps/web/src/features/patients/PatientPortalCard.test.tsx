import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { PatientProfile } from "./PatientProfile";
import { PATIENT_ID, patient, renderInWorkspace, workspaceRoutes } from "./testing";

const qrTexts: string[] = [];
vi.mock("qrcode", () => ({
  default: {
    toDataURL: async (text: string) => {
      qrTexts.push(text);
      return "data:image/png;base64,AAAA";
    },
  },
}));
vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const ONE = `/api/v1/patients/${PATIENT_ID}`;
const URL = "http://localhost:3000/portal/link/secret-invite-token";
const NOT_LINKED = { status: "NOT_LINKED", method: null, linked_at: null, invite_expires_at: null };
const LINKED = { status: "LINKED", method: "INVITE", linked_at: "2026-10-24T05:30:00Z", invite_expires_at: null };

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  qrTexts.length = 0;
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

async function card() {
  renderInWorkspace(<PatientProfile patientId={PATIENT_ID} />);
  return screen.findByRole("region", { name: "Patient app" }, { timeout: 5000 });
}

describe("Patient app card (M6b-P1, decision 8A)", () => {
  it("R1: invites, shows the link once with its QR code, and says it expires", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      [`GET ${ONE}`]: () => json(200, patient()),
      [`GET ${ONE}/portal`]: () => json(200, NOT_LINKED),
      [`POST ${ONE}/portal-invite`]: () => json(201, { url: URL, expires_at: "2026-10-31T05:30:00Z" }),
    });
    const region = await card();
    expect(await within(region).findByText(/Not linked/)).toBeInTheDocument();

    fireEvent.click(within(region).getByRole("button", { name: "Invite to the patient app" }));

    expect(await within(region).findByTestId("portal-invite-link")).toHaveValue(URL);
    expect(await within(region).findByRole("img", { name: /QR code/ })).toBeInTheDocument();
    expect(qrTexts).toEqual([URL]);
    expect(within(region).getByText(/Invited, link expires/)).toHaveTextContent("31 Oct 2026");
    expect(within(region).getByRole("button", { name: "Invite again" })).toBeInTheDocument();
    const call = api.calls.find((c) => c.method === "POST");
    expect(call?.headers.get("X-CSRF-Token")).toBe("csrf-token");
  });

  it("R14: a linked record says how and since when; unlinking asks first", async () => {
    mockApi({
      ...workspaceRoutes,
      [`GET ${ONE}`]: () => json(200, patient()),
      [`GET ${ONE}/portal`]: () => json(200, LINKED),
      [`DELETE ${ONE}/portal-link`]: () => json(200, NOT_LINKED),
    });
    const region = await card();
    expect(await within(region).findByText(/Linked by invite since/)).toBeInTheDocument();

    fireEvent.click(within(region).getByRole("button", { name: "Unlink" }));
    expect(within(region).getByText(/no longer see this clinic/)).toBeInTheDocument();
    fireEvent.click(within(region).getByRole("button", { name: "Yes, unlink" }));

    expect(await within(region).findByText(/Not linked/)).toBeInTheDocument();
  });

  it("R4: an already linked record shows the API's answer", async () => {
    mockApi({
      ...workspaceRoutes,
      [`GET ${ONE}`]: () => json(200, patient()),
      [`GET ${ONE}/portal`]: () => json(200, NOT_LINKED),
      [`POST ${ONE}/portal-invite`]: () =>
        apiError(409, "PRT_ALREADY_LINKED", "These records can't be linked to this account."),
    });
    const region = await card();
    fireEvent.click(await within(region).findByRole("button", { name: "Invite to the patient app" }));
    expect(await within(region).findByRole("alert")).toHaveTextContent("can't be linked");
    expect(within(region).queryByTestId("portal-invite-link")).not.toBeInTheDocument();
  });
});
