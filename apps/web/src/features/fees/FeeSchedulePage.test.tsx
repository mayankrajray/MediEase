import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { FeeSchedulePage } from "./FeeSchedulePage";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const DOCTOR = "0192f0a0-0000-7000-8000-0000000000d1";
const CONSULT = "0192f0a0-0000-7000-8000-0000000000s1";
const FOLLOW = "0192f0a0-0000-7000-8000-0000000000s2";

const service = (id: string, name: string, kind: string, position: number, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  kind,
  default_price_paise: null,
  active: true,
  position,
  doctor_prices: [{ doctor_id: DOCTOR, own_price_paise: null, price_paise: null }],
  ...extra,
});

const schedule = (services: readonly unknown[]) => ({
  services,
  doctors: [{ id: DOCTOR, display_name: "Dr. Sample Doctor" }],
});

const DEFAULTS = [service(CONSULT, "Consultation", "CONSULTATION", 1), service(FOLLOW, "Follow-up", "FOLLOW_UP", 2)];

const owner = () => person([membership(CLINIC_A, "Alpha Clinic", "OWNER", { permissions: ["BILLING_MANAGE", "FEES_MANAGE"] })]);
const desk = () => person([membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", { permissions: ["BILLING_MANAGE"] })]);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
});

afterEach(() => vi.unstubAllGlobals());

describe("the fee schedule (M6d-P1, FR-BIL-01, billing R1-R4)", () => {
  it("AC1: the owner prices the consultation in rupees and the API gets paise", async () => {
    const priced = schedule([
      service(CONSULT, "Consultation", "CONSULTATION", 1, {
        default_price_paise: 50050,
        doctor_prices: [{ doctor_id: DOCTOR, own_price_paise: null, price_paise: 50050 }],
      }),
      DEFAULTS[1],
    ]);
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/fees": () => json(200, schedule(DEFAULTS)),
      [`PATCH /api/v1/clinic/fees/services/${CONSULT}`]: () => json(200, priced),
    });
    renderInWorkspace(<FeeSchedulePage />);
    const price = await screen.findByLabelText("Default price in rupees", { selector: `#price-${CONSULT}` });
    fireEvent.change(price, { target: { value: "500.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Consultation" }));
    expect(await screen.findByText("Consultation saved.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ name: "Consultation", kind: "CONSULTATION", default_price_paise: 50050 });
    const table = screen.getByRole("table", { name: "Prices by service and doctor" });
    expect(within(table).getAllByText("₹500.50")).toHaveLength(2);
  });

  it("refuses a price the API would refuse, before sending it", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/fees": () => json(200, schedule(DEFAULTS)),
    });
    renderInWorkspace(<FeeSchedulePage />);
    const price = await screen.findByLabelText("Default price in rupees", { selector: `#price-${CONSULT}` });
    fireEvent.change(price, { target: { value: "100000.01" } });
    expect(price).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Save Consultation" })).toBeDisabled();
    expect(api.calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("AC2: a doctor's own price, and clearing it back to the default", async () => {
    const own = schedule([
      service(CONSULT, "Consultation", "CONSULTATION", 1, {
        doctor_prices: [{ doctor_id: DOCTOR, own_price_paise: 70000, price_paise: 70000 }],
      }),
      DEFAULTS[1],
    ]);
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/fees": () => json(200, schedule(DEFAULTS)),
      [`PUT /api/v1/clinic/fees/services/${CONSULT}/doctors/${DOCTOR}`]: () => json(200, own),
    });
    renderInWorkspace(<FeeSchedulePage />);
    const input = await screen.findByLabelText("Dr. Sample Doctor's price for Consultation, in rupees");
    fireEvent.change(input, { target: { value: "700" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Dr. Sample Doctor's price for Consultation" }));
    expect(await screen.findByText("Dr. Sample Doctor's price for Consultation saved.")).toBeInTheDocument();
    expect(screen.getByText("(own price)")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Dr. Sample Doctor's price for Consultation" }));
    expect(await screen.findByText("Dr. Sample Doctor now charges the default for Consultation.")).toBeInTheDocument();
    expect(api.calls.filter((c) => c.method === "PUT").map((c) => c.body)).toEqual([{ price_paise: 70000 }, { price_paise: null }]);
  });

  it("adds a service, and shows the API's refusal of a taken name", async () => {
    let added = 0;
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/fees": () => json(200, schedule(DEFAULTS)),
      "POST /api/v1/clinic/fees/services": () =>
        ++added === 1
          ? json(201, schedule([...DEFAULTS, service("0192f0a0-0000-7000-8000-0000000000s3", "Dressing", "PROCEDURE", 3, { default_price_paise: 20000 })]))
          : apiError(409, "BIL_SERVICE_NAME_TAKEN", "Another active service already has this name."),
    });
    renderInWorkspace(<FeeSchedulePage />);
    const name = await screen.findByLabelText(/^Name/, { selector: "#new-service-name" });
    fireEvent.change(name, { target: { value: "Dressing" } });
    fireEvent.change(screen.getByLabelText("Default price in rupees", { selector: "#new-service-price" }), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Add service" }));
    expect(await screen.findByText("Dressing added.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Dressing", kind: "PROCEDURE", default_price_paise: 20000 });
    expect(name).toHaveValue("");

    fireEvent.change(name, { target: { value: "dressing" } });
    fireEvent.click(screen.getByRole("button", { name: "Add service" }));
    expect(await screen.findByText(/Another active service already has this name/)).toBeInTheDocument();
  });

  it("retires a service and restores it", async () => {
    const retired = schedule([DEFAULTS[0], { ...DEFAULTS[1], active: false }]);
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, owner()),
      "GET /api/v1/clinic/fees": () => json(200, schedule(DEFAULTS)),
      [`PATCH /api/v1/clinic/fees/services/${FOLLOW}`]: (request) =>
        json(200, (request.body as { active?: boolean }).active === false ? retired : schedule(DEFAULTS)),
    });
    renderInWorkspace(<FeeSchedulePage />);
    fireEvent.click(await screen.findByRole("button", { name: "Retire Follow-up" }));
    expect(await screen.findByText("Follow-up retired.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restore Follow-up" }));
    expect(await screen.findByText("Follow-up restored.")).toBeInTheDocument();
  });

  it("AC3: the front desk reads the prices but cannot change them", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, desk()),
      "GET /api/v1/clinic/fees": () => json(200, schedule(DEFAULTS)),
    });
    renderInWorkspace(<FeeSchedulePage />);
    const table = await screen.findByRole("table", { name: "Prices by service and doctor" });
    expect(within(table).getByText("Consultation")).toBeInTheDocument();
    expect(within(table).getAllByText("No price").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Add service" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Save/ })).toBeNull();
  });
});
