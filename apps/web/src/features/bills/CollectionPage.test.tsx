import { screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { CollectionPage } from "./CollectionPage";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const tally = (payments: number, refunds: number, count: number) => ({
  payments_paise: payments,
  refunds_paise: refunds,
  net_paise: payments - refunds,
  count,
});
const desk = () => person([membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", { permissions: ["BILLING_MANAGE", "COLLECTION_VIEW"] })]);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => vi.unstubAllGlobals());

describe("the daily collection (M6d-P5, billing R55-R62)", () => {
  it("AC16: shows the net, the modes, the doctors and the entries, voided ones uncounted", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      "GET /api/v1/clinic/collection": () =>
        json(200, {
          date: "2026-10-26",
          timezone: "Asia/Kolkata",
          total: tally(100000, 20000, 4),
          voided: tally(10000, 0, 1),
          by_mode: [
            { mode: "CASH", ...tally(40000, 20000, 2) },
            { mode: "UPI", ...tally(30000, 0, 1) },
            { mode: "CARD", ...tally(30000, 0, 1) },
          ],
          by_doctor: [{ doctor: { id: "d1", display_name: "Dr. Sample Doctor" }, ...tally(100000, 20000, 4) }],
          items: [
            {
              id: "p1",
              bill_id: "b1",
              bill_number: "SC/26-27/0001",
              kind: "PAYMENT",
              mode: "UPI",
              amount_paise: 30000,
              reference: "UPI-1",
              received_at: "2026-10-26T05:00:00+00:00",
              received_by: "Sample Desk",
              patient: { id: "pt", code: "SC-0001", full_name: "Asha Rao" },
              doctor: null,
              voided: false,
            },
          ],
        }),
    });
    renderInWorkspace(<CollectionPage />);
    expect(await screen.findByText(/Net ₹800.00/)).toBeInTheDocument();
    expect(screen.getByText(/1 voided, not counted/)).toBeInTheDocument();
    const modes = screen.getByRole("table", { name: "Collection by mode" });
    expect(within(modes).getByText("UPI")).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Collection by doctor" })).getByText("Dr. Sample Doctor")).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Every payment and refund of the day" })).getByText("SC/26-27/0001")).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === "/api/v1/clinic/collection")?.search.get("date")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
