import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import type { AuditEntry, AuditPage } from "./api";
import { AuditLog } from "./AuditLog";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const owner = membership(CLINIC_A, "Alpha Clinic", "OWNER", { permissions: ["CLINIC_VIEW", "AUDIT_VIEW"] });
const desk = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", { permissions: ["CLINIC_VIEW"] });

function entry(n: number, overrides: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: `0192f0a0-0000-7000-8000-${String(n).padStart(12, "0")}`,
    occurred_at: "2026-10-22T05:00:00+00:00",
    action: "appointment.cancelled",
    action_label: "Cancelled an appointment",
    category: "APPOINTMENTS",
    actor: { type: "STAFF", user_id: "0192f0a0-0000-7000-8000-0000000000aa", label: "Sample Desk", role: "FRONT_DESK" },
    entity_type: "appointment",
    entity_id: "0192f0a0-0000-7000-8000-0000000000bb",
    patient_code: null,
    metadata: { cancel_reason: "PATIENT_REQUEST" },
    ...overrides,
  };
}

function page(items: readonly AuditEntry[], next: string | null = null): AuditPage {
  return {
    from: "2026-10-16",
    to: "2026-10-22",
    timezone: "Asia/Kolkata",
    items: [...items],
    next_cursor: next,
    categories: [
      { value: "APPOINTMENTS", label: "Appointments" },
      { value: "PATIENTS", label: "Patients" },
    ],
  };
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  vi.unstubAllGlobals();
});

describe("the owner's audit log (M6a-P8, FR-AUD-03, decision 8A)", () => {
  it("shows who did what in words, filters by category and loads more", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, person([owner])),
      "GET /api/v1/audit-events": (call) =>
        json(
          200,
          call.search.get("cursor") === "next"
            ? page([entry(2, { action: "patient.created", action_label: "Registered a patient", category: "PATIENTS", patient_code: "SC-0004", entity_type: "patient" })])
            : page([entry(1)], "next"),
        ),
    });
    renderInWorkspace(<AuditLog />);

    const table = await screen.findByRole("table", { name: "Audit log entries, newest first" }, { timeout: 5000 });
    const [first] = within(table).getAllByRole("row").slice(1);
    expect(first).toHaveTextContent("Sample Desk");
    expect(first).toHaveTextContent("Front desk");
    expect(first).toHaveTextContent("Cancelled an appointment");
    expect(first).toHaveTextContent("cancel reason: PATIENT_REQUEST");

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await within(table).findByText("Patient SC-0004")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "APPOINTMENTS" } });
    fireEvent.click(screen.getByRole("button", { name: "Show" }));
    await waitFor(() => expect(api.calls.some((c) => c.search.get("category") === "APPOINTMENTS")).toBe(true));
  });

  it("exports the range as a CSV file", async () => {
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/me": () => json(200, person([owner])),
      "GET /api/v1/audit-events": () => json(200, page([entry(1)])),
      "GET /api/v1/audit-events/export": () =>
        new Response("Time,Person\n", {
          status: 200,
          headers: { "Content-Type": "text/csv", "Content-Disposition": 'attachment; filename="audit-alpha-2026-10-16-2026-10-22.csv"' },
        }),
    });
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:audit"), revokeObjectURL: vi.fn() });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderInWorkspace(<AuditLog />);

    fireEvent.click(await screen.findByRole("button", { name: "Export CSV" }, { timeout: 5000 }));

    expect(await screen.findByText("Exported audit-alpha-2026-10-16-2026-10-22.csv.")).toBeInTheDocument();
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("failure path: the front desk is told the log is for owners, and nothing is fetched", async () => {
    const api = mockApi({ ...workspaceRoutes, "GET /api/v1/me": () => json(200, person([desk])) });
    renderInWorkspace(<AuditLog />);
    expect(await screen.findByRole("alert", undefined, { timeout: 5000 })).toHaveTextContent("The audit log is for the clinic's owners");
    expect(api.count("GET /api/v1/audit-events")).toBe(0);
  });
});
