import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PortalAssistant } from "@/features/assistant/PortalAssistant";
import { me, renderPortal } from "@/features/portal/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi, type Recorded } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const ID = "0192f3a4-0000-7b2a-9d40-5e6f7a8b9c0d";
const CODE = "0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d";
const UPL = "/api/v1/portal/prescription-uploads";
const TURNS = "POST /api/v1/portal/assistant/turns";

function upload(state: string, extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    state,
    source: "FILE",
    rejection_code: null,
    attempts_left: null,
    created_at: "2026-10-27T05:00:00+00:00",
    verification: null,
    ...extra,
  };
}

function verified(extra: Record<string, unknown> = {}) {
  return upload("VERIFIED", {
    verification: {
      access: "OWN",
      clinic_name: "Sample Clinic",
      doctor_name: "Dr. Mehta",
      version: 1,
      issued_at: "2026-10-20T05:00:00+00:00",
      superseded: false,
      latest_version: null,
      latest_issued_at: null,
      selected: "UPLOADED",
      expires_at: "2026-10-28T05:00:00+00:00",
      ...extra,
    },
  });
}

const base = {
  ...me(),
  "GET /api/v1/portal/links": () => json(200, { items: [] }),
  "GET /api/v1/portal/prescriptions": () => json(200, { items: [] }),
};

function contextOf(calls: readonly Recorded[]): unknown {
  const turns = calls.filter((c) => `${c.method} ${c.path}` === TURNS);
  return (turns.at(-1)?.body as { context: unknown } | undefined)?.context;
}

function ask(text: string) {
  fireEvent.change(screen.getByLabelText("Your message"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

function typeCode(code = CODE) {
  fireEvent.change(screen.getByLabelText("Verification code"), { target: { value: code } });
  fireEvent.click(screen.getByRole("button", { name: "Check code" }));
}

beforeEach(() => {
  resetRefreshState();
  resetNavigation();
});

describe("prescription uploads on the assistant page (M7b; FR-UPL-01..05)", () => {
  it("FR-UPL-01 a file is uploaded, checked until verified, then is the turn's context", async () => {
    const api = mockApi({
      ...base,
      [`POST ${UPL}`]: () => json(202, upload("QUARANTINED")),
      [`GET ${UPL}/${ID}`]: [() => json(200, upload("SCANNING")), () => json(200, verified())],
      [TURNS]: () => json(200, { kind: "ANSWER", reply: "1. Syrup X", proposal: null }),
    });
    await renderPortal(<PortalAssistant />);
    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "rx.pdf", { type: "application/pdf" });
    fireEvent.change(await screen.findByLabelText("Photo or PDF of the prescription"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByText("Checking your file…")).toBeInTheDocument();
    expect(
      await screen.findByText("Verified: Dr. Mehta, Sample Clinic, 20 Oct 2026 (version 1).", {}, { timeout: 6000 }),
    ).toBeInTheDocument();
    expect(screen.getByText(/The file is deleted once it is checked/)).toBeInTheDocument();
    ask("Explain it");
    await waitFor(() => expect(contextOf(api.calls)).toEqual({ upload_id: ID }));
  }, 10_000);

  it("FR-UPL-04 someone else's prescription asks for the last 4 digits, counts down, then verifies", async () => {
    const api = mockApi({
      ...base,
      [`POST ${UPL}/by-code`]: () => json(201, upload("NEEDS_CHALLENGE", { source: "CODE", attempts_left: 5 })),
      [`POST ${UPL}/${ID}/challenge`]: [
        () =>
          json(401, {
            error: { code: "UPL_CHALLENGE_FAILED", message: "no", request_id: "r", details: { attempts_left: "4" } },
          }),
        () => json(200, verified({ access: "REPRESENTATIVE" })),
      ],
    });
    await renderPortal(<PortalAssistant />);
    await screen.findByLabelText("Verification code");
    typeCode();
    const digits = await screen.findByLabelText("Last 4 digits of the patient's phone");
    fireEvent.change(digits, { target: { value: "12a34" } });
    expect(digits).toHaveValue("1234");
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("That did not match. 4 attempts left.")).toBeInTheDocument();
    fireEvent.change(digits, { target: { value: "0101" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(/It has not been added to your account/)).toBeInTheDocument();
    const bodies = api.calls.filter((c) => c.path === `${UPL}/${ID}/challenge`).map((c) => c.body);
    expect(bodies).toEqual([{ phone_last4: "1234" }, { phone_last4: "0101" }]);
  });

  it("FR-UPL-05 an older version is never chosen for the user; the choice becomes the context", async () => {
    const older = { superseded: true, latest_version: 2, latest_issued_at: "2026-10-25T05:00:00+00:00", selected: null };
    const api = mockApi({
      ...base,
      [`POST ${UPL}/by-code`]: () => json(201, verified(older)),
      [`POST ${UPL}/${ID}/selection`]: () => json(200, verified({ ...older, selected: "LATEST" })),
      [TURNS]: () => json(200, { kind: "ANSWER", reply: "ok", proposal: null }),
    });
    await renderPortal(<PortalAssistant />);
    await screen.findByLabelText("Verification code");
    typeCode();
    const group = await screen.findByRole("group", { name: /This is an older version \(version 1\)/ });
    ask("Explain it");
    await waitFor(() => expect(contextOf(api.calls)).toBeNull()); // nothing chosen yet
    fireEvent.click(within(group).getByRole("button", { name: "The latest (version 2)" }));
    expect(await screen.findByText("The assistant will explain version 2.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === `${UPL}/${ID}/selection`)?.body).toEqual({ choice: "LATEST" });
    ask("Explain it");
    await waitFor(() => expect(contextOf(api.calls)).toEqual({ upload_id: ID }));
  });

  it("NFR-20 a rejected file says why and offers the forms again; Remove withdraws", async () => {
    const api = mockApi({
      ...base,
      [`POST ${UPL}/by-code`]: [
        () => json(201, upload("REJECTED", { rejection_code: "UPL_INFECTED" })),
        () => json(201, verified()),
      ],
      [`DELETE ${UPL}/${ID}`]: () => new Response(null, { status: 204 }),
    });
    await renderPortal(<PortalAssistant />);
    await screen.findByLabelText("Verification code");
    typeCode();
    expect(await screen.findByText("The file was refused by the safety check and deleted.")).toBeInTheDocument();
    typeCode();
    await screen.findByText(/^Verified:/);
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() => expect(api.count(`DELETE ${UPL}/${ID}`)).toBe(1));
    expect(await screen.findByLabelText("Verification code")).toBeInTheDocument();
  });

  it("an upload refused by the API shows its message", async () => {
    mockApi({
      ...base,
      [`POST ${UPL}/by-code`]: () => apiError(429, "UPL_RATE_LIMITED", "Too many uploads. Please try again later."),
    });
    await renderPortal(<PortalAssistant />);
    await screen.findByLabelText("Verification code");
    typeCode();
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many uploads. Please try again later.");
  });
});
