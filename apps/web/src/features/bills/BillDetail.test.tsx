import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { BillDetail } from "./BillDetail";
import { BillsList } from "./BillsList";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const BILL = "0192f0a0-0000-7000-8000-0000000000b1";
const DOCTOR = "0192f0a0-0000-7000-8000-0000000000d1";
const SERVICE = "0192f0a0-0000-7000-8000-0000000000s1";
const LINE = "0192f0a0-0000-7000-8000-0000000000l1";
const LINE2 = "0192f0a0-0000-7000-8000-0000000000l2";

const line = (id: string, description: string, amount: number, extra: Record<string, unknown> = {}) => ({
  id,
  position: 1,
  service_id: null,
  description,
  unit_price_paise: amount,
  quantity: 1,
  discount: { kind: "NONE", value: 0 },
  discount_paise: 0,
  bill_discount_paise: 0,
  amount_paise: amount,
  credited: false,
  ...extra,
});

const bill = (extra: Record<string, unknown> = {}) => ({
  id: BILL,
  status: "DRAFT",
  number: null,
  bill_date: null,
  patient: { id: "0192f0a0-0000-7000-8000-0000000000p1", code: "SC-0001", full_name: "Asha Rao" },
  doctor: { id: DOCTOR, display_name: "Dr. Sample Doctor" },
  visit_id: null,
  total_paise: 50000,
  credited_paise: 0,
  paid_paise: 0,
  refunded_paise: 0,
  balance_paise: null,
  created_at: "2026-10-26T06:00:00+00:00",
  issued_at: null,
  lines: [line(LINE, "Consultation", 50000, { service_id: SERVICE })],
  discount: { kind: "NONE", value: 0 },
  subtotal_paise: 50000,
  discount_paise: 0,
  notes: null,
  updated_at: "2026-10-26T06:00:00+00:00",
  credit_notes: [],
  ...extra,
});

const fees = {
  services: [
    {
      id: SERVICE,
      name: "Consultation",
      kind: "CONSULTATION",
      default_price_paise: 50000,
      active: true,
      position: 1,
      doctor_prices: [{ doctor_id: DOCTOR, own_price_paise: 60000, price_paise: 60000 }],
    },
  ],
  doctors: [{ id: DOCTOR, display_name: "Dr. Sample Doctor" }],
};

const desk = () => person([membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", { permissions: ["BILLING_MANAGE", "PATIENTS_MANAGE"] })]);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => vi.unstubAllGlobals());

describe("a bill (M6d-P2, billing R13-R30)", () => {
  it("AC5: edits a draft in rupees, sends paise and issues it", async () => {
    const issued = bill({ status: "ISSUED", number: "SC/26-27/0001", bill_date: "2026-10-26", balance_paise: 45000, total_paise: 45000 });
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      [`GET /api/v1/clinic/bills/${BILL}`]: () => json(200, bill()),
      "GET /api/v1/clinic/fees": () => json(200, fees),
      [`PUT /api/v1/clinic/bills/${BILL}`]: () => json(200, bill({ total_paise: 45000 })),
      [`POST /api/v1/clinic/bills/${BILL}/issue`]: () => json(200, issued),
    });
    renderInWorkspace(<BillDetail billId={BILL} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a line" }));
    fireEvent.change(screen.getByLabelText("Line 2: description"), { target: { value: "Dressing" } });
    fireEvent.change(screen.getByLabelText("Line 2: price in rupees"), { target: { value: "150.5" } });
    fireEvent.change(screen.getByLabelText("Bill discount"), { target: { value: "PERCENT" } });
    fireEvent.change(screen.getByLabelText("Bill discount: percent"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Issue bill" }));
    expect(await screen.findByText("Bill issued. It can no longer change.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      lines: [
        { service_id: SERVICE, description: "Consultation", unit_price_paise: 50000, quantity: 1, discount: { kind: "NONE", value: 0 } },
        { description: "Dressing", unit_price_paise: 15050, quantity: 1, discount: { kind: "NONE", value: 0 } },
      ],
      discount: { kind: "PERCENT", value: 1000 },
      notes: null,
    });
    expect(screen.getByRole("heading", { name: "Bill SC/26-27/0001" })).toBeInTheDocument();
    expect(screen.getByText("₹450.00 due")).toBeInTheDocument();
  });

  it("takes the doctor's own price when a service is chosen, and refuses a bad price before sending", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      [`GET /api/v1/clinic/bills/${BILL}`]: () => json(200, bill({ lines: [] })),
      "GET /api/v1/clinic/fees": () => json(200, fees),
    });
    renderInWorkspace(<BillDetail billId={BILL} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add a line" }));
    await screen.findByRole("option", { name: "Consultation" });
    fireEvent.change(screen.getByLabelText("Line 1: service"), { target: { value: SERVICE } });
    expect(screen.getByLabelText("Line 1: price in rupees")).toHaveValue("600");
    fireEvent.change(screen.getByLabelText("Line 1: price in rupees"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Enter rupees up to 1,00,000, with at most two decimals.")).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("AC6: credits chosen lines with a reason, and cancels the rest", async () => {
    const issued = bill({
      status: "ISSUED",
      number: "SC/26-27/0001",
      bill_date: "2026-10-26",
      total_paise: 70000,
      balance_paise: 70000,
      lines: [line(LINE, "Consultation", 50000), line(LINE2, "Dressing", 20000)],
    });
    const credited = {
      ...issued,
      credited_paise: 20000,
      balance_paise: 50000,
      lines: [line(LINE, "Consultation", 50000), line(LINE2, "Dressing", 20000, { credited: true })],
      credit_notes: [
        {
          id: "cn1",
          number: "SC/CN/26-27/0001",
          bill_date: "2026-10-26",
          reason: "Not done",
          total_paise: 20000,
          issued_at: "2026-10-26T07:00:00+00:00",
          lines: [{ id: "x", credits_line_id: LINE2, description: "Dressing", amount_paise: 20000 }],
        },
      ],
    };
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      [`GET /api/v1/clinic/bills/${BILL}`]: () => json(200, issued),
      [`POST /api/v1/clinic/bills/${BILL}/credit-notes`]: () => json(201, credited),
    });
    renderInWorkspace(<BillDetail billId={BILL} />);
    fireEvent.click(await screen.findByLabelText("Dressing (₹200.00)"));
    fireEvent.click(screen.getByRole("button", { name: "Credit the chosen lines" }));
    expect(await screen.findByText("Say why the bill is corrected.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Reason/), { target: { value: "Not done" } });
    fireEvent.click(screen.getByRole("button", { name: "Credit the chosen lines" }));
    expect(await screen.findByText("Credit note issued.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ line_ids: [LINE2], reason: "Not done" });
    expect(screen.getByText(/SC\/CN\/26-27\/0001/)).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Bill lines" })).getByText("Credited")).toBeInTheDocument();
  });

  it("shows the API's refusal", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      [`GET /api/v1/clinic/bills/${BILL}`]: () => json(200, bill()),
      "GET /api/v1/clinic/fees": () => json(200, fees),
      [`PUT /api/v1/clinic/bills/${BILL}`]: () => apiError(409, "BIL_NOT_DRAFT", "Only a draft bill can be changed, discarded or issued."),
    });
    renderInWorkspace(<BillDetail billId={BILL} />);
    fireEvent.click(await screen.findByRole("button", { name: "Save draft" }));
    expect(await screen.findByText(/Only a draft bill can be changed/)).toBeInTheDocument();
  });
});

describe("the bills list (M6d-P2, billing R22)", () => {
  it("lists bills with their balance and starts a new one for a picked patient", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      "GET /api/v1/clinic/bills": () => json(200, { items: [bill({ status: "ISSUED", number: "SC/26-27/0001", balance_paise: 30000 })], next_cursor: null }),
      "GET /api/v1/patients": () =>
        json(200, { items: [{ ...bill().patient, phone_e164: "+919000000001", sex: "FEMALE", date_of_birth: "1990-01-01", age_years: 36, is_minor: false }] }),
      "POST /api/v1/clinic/bills": () => json(201, bill()),
    });
    renderInWorkspace(<BillsList />);
    const table = await screen.findByRole("table", { name: "Bills" });
    expect(within(table).getByRole("link", { name: "SC/26-27/0001" })).toHaveAttribute("href", `/bills/${BILL}`);
    expect(within(table).getByText("₹300.00 due")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "New bill" }));
    expect(screen.getByText("Who is the bill for?")).toBeInTheDocument();
  });

  it("says when there are no bills", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      "GET /api/v1/clinic/bills": () => json(200, { items: [], next_cursor: null }),
    });
    renderInWorkspace(<BillsList />);
    expect(await screen.findByText("No bills yet.")).toBeInTheDocument();
  });
});
