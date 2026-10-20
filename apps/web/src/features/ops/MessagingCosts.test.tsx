import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { CLINIC_A, ops } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { MessagingCosts, currentMonth } from "./MessagingCosts";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const COSTS = "GET /api/v1/ops/messaging-costs";
const base = { "GET /api/v1/me": () => json(200, ops()) };

const costs = (month: string) => ({
  month,
  cost_paise: 12,
  clinics: [
    {
      clinic_id: CLINIC_A,
      clinic_name: "Alpha Clinic",
      messages: 4,
      unpriced: 2,
      cost_paise: 12,
      channels: [
        { channel: "WHATSAPP", messages: 3, priced: 1, unpriced: 2, cost_paise: 12 },
        { channel: "SMS", messages: 1, priced: 1, unpriced: 0, cost_paise: 0 },
      ],
    },
  ],
});

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => {
  vi.useRealTimers();
});

function renderCosts() {
  return render(
    <SessionProvider>
      <MessagingCosts />
    </SessionProvider>,
  );
}

describe("ops messaging costs (R18; M5-P6 decision 6A)", () => {
  it("defaults to this month in India", () => {
    expect(currentMonth(new Date("2026-10-31T18:31:00Z"))).toBe("2026-11"); // 00:01 IST on 1 Nov
    expect(currentMonth(new Date("2026-10-31T18:29:00Z"))).toBe("2026-10");
  });

  it("shows each clinic's total and channels in rupees, excluding GST, and loads another month", async () => {
    const api = mockApi({ ...base, [COSTS]: (call) => json(200, costs(call.search.get("month") ?? "")) });
    renderCosts();

    expect(await screen.findByText("Total: ₹0.12", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText(/excluding GST/)).toBeInTheDocument();
    const [clinic] = screen.getAllByRole("row", { name: /^Alpha Clinic/ });
    expect(clinic).toHaveTextContent("All");
    expect(clinic).toHaveTextContent("4");
    expect(clinic).toHaveTextContent("₹0.12");
    const whatsapp = screen.getByRole("row", { name: /WhatsApp/ });
    expect(within(whatsapp).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Alpha Clinic", "3", "2", "₹0.12"]);
    expect(api.calls.find((c) => c.path === "/api/v1/ops/messaging-costs")?.search.get("month")).toBe(currentMonth());

    fireEvent.change(screen.getByLabelText("Month"), { target: { value: "2026-09" } });
    expect(await screen.findByText("Total: ₹0.12")).toBeInTheDocument();
    expect(api.calls.at(-1)?.search.get("month")).toBe("2026-09");
  });

  it("says so for a month without messages, and a failure shows the Ref", async () => {
    mockApi({
      ...base,
      [COSTS]: [() => apiError(500, "SYS_INTERNAL", "Something went wrong."), () => json(200, { month: "2026-10", cost_paise: 0, clinics: [] })],
    });
    renderCosts();

    expect(await screen.findByRole("alert", {}, { timeout: 5000 })).toHaveTextContent("Ref: test-ref");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No messages were sent in this month.")).toBeInTheDocument();
  });
});
