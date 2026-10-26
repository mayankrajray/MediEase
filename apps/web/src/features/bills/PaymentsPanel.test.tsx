import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { DuesPage } from "./DuesPage";
import type { Bill } from "./api";
import { PaymentsPanel } from "./PaymentsPanel";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const BILL = "0192f0a0-0000-7000-8000-0000000000b1";

const bill = (extra: Record<string, unknown> = {}): Bill =>
  ({
    id: BILL,
    status: "ISSUED",
    number: "SC/26-27/0001",
    bill_date: "2026-10-26",
    patient: { id: "0192f0a0-0000-7000-8000-0000000000p1", code: "SC-0001", full_name: "Asha Rao" },
    doctor: null,
    visit_id: null,
    total_paise: 50000,
    credited_paise: 0,
    paid_paise: 0,
    refunded_paise: 0,
    balance_paise: 50000,
    created_at: "2026-10-26T06:00:00+00:00",
    issued_at: "2026-10-26T06:00:00+00:00",
    lines: [],
    discount: { kind: "NONE", value: 0 },
    subtotal_paise: 50000,
    discount_paise: 0,
    notes: null,
    updated_at: "2026-10-26T06:00:00+00:00",
    credit_notes: [],
    payments: [],
    ...extra,
  }) as unknown as Bill;

const payment = (extra: Record<string, unknown> = {}) => ({
  id: "0192f0a0-0000-7000-8000-0000000000y1",
  kind: "PAYMENT",
  mode: "UPI",
  amount_paise: 20000,
  reference: "UPI-1",
  received_at: "2026-10-26T06:30:00+00:00",
  local_date: new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" }),
  received_by: "Sample Desk",
  voided_at: null,
  voided_by: null,
  void_reason: null,
  ...extra,
});

const desk = () => person([membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", { permissions: ["BILLING_MANAGE", "COLLECTION_VIEW"] })]);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => vi.unstubAllGlobals());

describe("payments on a bill (M6d-P3, billing R31-R36)", () => {
  it("AC9: takes a UPI payment in rupees with its reference", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      [`POST /api/v1/clinic/bills/${BILL}/payments`]: () => json(201, bill({ paid_paise: 20000, balance_paise: 30000, payments: [payment()] })),
    });
    const onChange = vi.fn();
    renderInWorkspace(<PaymentsPanel bill={bill()} onChange={onChange} />);
    const amount = await screen.findByLabelText(/^Amount in rupees/);
    expect(amount).toHaveValue("500");
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "UPI" } });
    fireEvent.change(amount, { target: { value: "200" } });
    fireEvent.change(screen.getByLabelText("Reference (optional)"), { target: { value: "UPI-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Record payment" }));
    expect(await screen.findByText("Payment of ₹200.00 recorded.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ kind: "PAYMENT", mode: "UPI", amount_paise: 20000, reference: "UPI-1" });
    expect(onChange).toHaveBeenCalled();
  });

  it("AC10: offers a refund when a credit note leaves the bill overpaid, and shows a refusal", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      [`POST /api/v1/clinic/bills/${BILL}/payments`]: () => apiError(409, "BIL_PAYMENT_TOO_LARGE", "This refund is more than the bill allows."),
    });
    renderInWorkspace(<PaymentsPanel bill={bill({ balance_paise: -20000, credited_paise: 20000, paid_paise: 50000 })} onChange={vi.fn()} />);
    expect(await screen.findByText("Refund ₹200.00 to the patient")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Record refund" }));
    expect(await screen.findByText(/This refund is more than the bill allows/)).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({ kind: "REFUND", amount_paise: 20000 });
  });

  it("AC11: voids today's payment with a reason; an older one has no Void", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      [`POST /api/v1/clinic/bills/${BILL}/payments/0192f0a0-0000-7000-8000-0000000000y1/void`]: () =>
        json(200, bill({ payments: [payment({ voided_at: "2026-10-26T07:00:00+00:00", voided_by: "Sample Desk", void_reason: "Wrong amount" })] })),
    });
    renderInWorkspace(
      <PaymentsPanel
        bill={bill({ paid_paise: 20000, balance_paise: 30000, payments: [payment(), payment({ id: "old", local_date: "2026-01-01", amount_paise: 100 })] })}
        onChange={vi.fn()}
      />,
    );
    expect(await screen.findAllByRole("button", { name: /^Void/ })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Void the ₹200.00 payment" }));
    fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: "Wrong amount" } });
    fireEvent.click(screen.getByRole("button", { name: "Void" }));
    expect(await screen.findByText("The ₹200.00 payment was voided.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ reason: "Wrong amount" });
  });
});

describe("the dues list (M6d-P3, billing R39)", () => {
  it("lists who owes, the largest first, with the total", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      "GET /api/v1/clinic/dues": () =>
        json(200, { total_paise: 40000, items: [{ patient: bill().patient, bills: 2, due_paise: 40000, oldest_bill_date: "2026-10-20" }] }),
    });
    renderInWorkspace(<DuesPage />);
    expect(await screen.findByText("In all: ₹400.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Asha Rao · SC-0001" })).toBeInTheDocument();
  });
});
