import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { ReceiptView } from "@/features/patient-link/ReceiptView";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import type { Bill } from "./api";
import { ReceiptPanel } from "./ReceiptPanel";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);
vi.mock("qrcode", () => ({ default: { toDataURL: () => Promise.resolve("data:image/png;base64,AAAA") } }));

const BILL = "0192f0a0-0000-7000-8000-0000000000b1";
const bill = { id: BILL, number: "SC/26-27/0001", status: "ISSUED" } as unknown as Bill;
const desk = () => person([membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", { permissions: ["BILLING_MANAGE"] })]);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => vi.unstubAllGlobals());

describe("the receipt panel (M6d-P4, billing R46, R48)", () => {
  it("AC14: shows the receipt link as a QR code with the address to copy", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      [`GET /api/v1/clinic/bills/${BILL}/link`]: () =>
        json(200, {
          id: "l1",
          url: "https://example.test/r/TOKEN",
          expires_at: "2027-01-01T00:00:00+00:00",
          locked: false,
          open_count: 0,
          last_opened_at: null,
        }),
    });
    renderInWorkspace(<ReceiptPanel bill={bill} />);
    fireEvent.click(await screen.findByRole("button", { name: "Show QR for the patient" }));
    expect(await screen.findByAltText("QR code of the patient's receipt link")).toBeInTheDocument();
    expect(screen.getByTestId("receipt-link")).toHaveTextContent("https://example.test/r/TOKEN");
    expect(screen.getByRole("button", { name: "Print bill" })).toBeEnabled();
  });
});

describe("the receipt page's content (M6d-P4, billing R49)", () => {
  it("shows the number, the amounts and the PDF link, and nothing clinical", () => {
    render(
      <ReceiptView
        receipt={{
          clinic_name: "Alpha Clinic",
          number: "SC/26-27/0001",
          bill_date: "2026-10-26",
          total_paise: 70000,
          credited_paise: 0,
          paid_paise: 20000,
          refunded_paise: 0,
          balance_paise: 50000,
          cancelled: false,
        }}
        pdfHref="/r/TOKEN/receipt.pdf"
      />,
    );
    expect(screen.getByRole("heading", { name: "Bill SC/26-27/0001" })).toBeInTheDocument();
    expect(screen.getByText("Balance due")).toBeInTheDocument();
    expect(screen.getByText("₹500.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download the receipt (PDF)" })).toHaveAttribute("href", "/r/TOKEN/receipt.pdf");
  });
});
