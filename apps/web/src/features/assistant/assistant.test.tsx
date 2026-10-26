import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PortalAssistant } from "@/features/assistant/PortalAssistant";
import { StaffAssistant } from "@/features/assistant/StaffAssistant";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { CLINIC_ID, link, me, renderPortal } from "@/features/portal/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi, type Recorded } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const RX = {
  id: "0192f3a4-7c1e-7b2a-9d40-5e6f7a8b9c0d",
  clinic_id: CLINIC_ID,
  clinic_name: "Sample Clinic",
  doctor_name: "Dr. Mehta",
  version: 1,
  issued_at: "2026-10-20T05:00:00+00:00",
};

const TURNS = "POST /api/v1/portal/assistant/turns";

function reply(kind: string, text: string, proposal: unknown = null) {
  return json(200, { kind, reply: text, proposal });
}

function sentTo(calls: readonly Recorded[], key: string): Recorded[] {
  return calls.filter((c) => `${c.method} ${c.path}` === key);
}

function ask(label: string, text: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

beforeEach(() => {
  resetRefreshState();
  resetNavigation();
});
afterEach(() => vi.unstubAllGlobals());

describe("the patient assistant (M7a-P4; FR-AI-01, 04)", () => {
  it("FR-AI-04 sends the chosen prescription as the context and shows the answer", async () => {
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/links": () => json(200, { items: [link()] }),
      "GET /api/v1/portal/prescriptions": () => json(200, { items: [RX] }),
      [TURNS]: () => reply("ANSWER", "1. Syrup X\n   - How much: 5 ml"),
    });
    await renderPortal(<PortalAssistant />);
    fireEvent.change(await screen.findByRole("combobox"), { target: { value: RX.id } });
    ask("Your message", "When do I take it?");
    const log = screen.getByRole("list", { name: "Conversation" });
    expect(await within(log).findByText(/How much: 5 ml/)).toBeInTheDocument();
    expect(sentTo(api.calls, TURNS)[0]?.body).toEqual({
      messages: [{ role: "user", content: "When do I take it?" }],
      language: "en",
      context: { prescription_id: RX.id },
    });
  });

  it("FR-AI-01 confirms a proposal only on Confirm, and Cancel changes nothing", async () => {
    const proposal = {
      token: "t".repeat(40),
      summary: "Send a booking request to Sample Clinic?",
      expires_at: "2026-10-27T10:10:00+00:00",
    };
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/links": () => json(200, { items: [] }),
      "GET /api/v1/portal/prescriptions": () => json(200, { items: [] }),
      [TURNS]: () => reply("CONFIRM", proposal.summary, proposal),
      "POST /api/v1/portal/assistant/confirm": () => reply("DONE", "Your request was sent."),
    });
    await renderPortal(<PortalAssistant />);
    await screen.findByText("No prescriptions in your account yet.");
    ask("Your message", "book it");
    const card = await screen.findByRole("group", { name: "Confirm" });
    fireEvent.click(within(card).getByRole("button", { name: "Cancel" }));
    expect(await screen.findByText("Nothing was changed.")).toBeInTheDocument();
    expect(api.count("POST /api/v1/portal/assistant/confirm")).toBe(0);

    ask("Your message", "book it again");
    const again = await screen.findByRole("group", { name: "Confirm" });
    fireEvent.click(within(again).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Your request was sent.")).toBeInTheDocument();
    expect(sentTo(api.calls, "POST /api/v1/portal/assistant/confirm")[0]?.body).toEqual({
      token: proposal.token,
      language: "en",
    });
    // The second turn carried the whole visible conversation, the last message the user's.
    const second = sentTo(api.calls, TURNS)[1]?.body as { messages: { role: string }[] };
    expect(second.messages.map((m) => m.role)).toEqual(["user", "assistant", "assistant", "user"]);
  });

  it("FR-AI-02 shows the referral, and an error with its reference", async () => {
    mockApi({
      ...me(),
      "GET /api/v1/portal/links": () => json(200, { items: [] }),
      "GET /api/v1/portal/prescriptions": () => json(200, { items: [] }),
      [TURNS]: [
        () => reply("REFERRAL", "I can't give medical advice."),
        () => apiError(503, "AI_UNAVAILABLE", "The assistant is not available right now."),
      ],
    });
    await renderPortal(<PortalAssistant />);
    await screen.findByText("No prescriptions in your account yet.");
    ask("Your message", "Should I double the dose?");
    expect(await screen.findByText("I can't give medical advice.")).toBeInTheDocument();
    ask("Your message", "hello");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The assistant is not available right now.");
    expect(alert).toHaveTextContent("test-ref");
  });
});

describe("the staff assistant (M7a-P5; FR-AI-01)", () => {
  it("FR-AI-01 sends the conversation and shows the reply", async () => {
    document.cookie = "me_csrf=csrf-token; path=/";
    const api = mockApi({
      ...workspaceRoutes,
      "POST /api/v1/assistant/turns": () => reply("ANSWER", "Queue for 2026-10-27:\nNo sessions."),
    });
    renderInWorkspace(<StaffAssistant />);
    fireEvent.change(await screen.findByLabelText("Message"), { target: { value: "show today's queue" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/Queue for 2026-10-27/)).toBeInTheDocument();
    await waitFor(() => expect(api.count("POST /api/v1/assistant/turns")).toBe(1));
    expect(sentTo(api.calls, "POST /api/v1/assistant/turns")[0]?.body).toEqual({
      messages: [{ role: "user", content: "show today's queue" }],
    });
  });
});
