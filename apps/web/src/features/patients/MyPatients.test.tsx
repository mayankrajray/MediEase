import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { MyPatients, type MyPatient } from "./MyPatients";
import { PATIENT_ID, renderInWorkspace, workspaceRoutes } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const URL = "GET /api/v1/my-patients";
const doctor = membership(CLINIC_A, "Alpha Clinic", "DOCTOR", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "PATIENTS_MANAGE", "CLINICAL_VIEW", "CLINICAL_WRITE"],
  doctor_id: "0192f0a0-0000-7000-8000-0000000000d1",
});

function mine(overrides: Partial<MyPatient> = {}): MyPatient {
  return {
    id: PATIENT_ID,
    code: "SC-0004",
    full_name: "Bina Shah",
    sex: "FEMALE",
    age_years: 47,
    age_is_estimated: true,
    last_visit_at: "2026-10-20T05:00:00+00:00",
    visits: 3,
    ...overrides,
  };
}

const routes = { ...workspaceRoutes, "GET /api/v1/me": () => json(200, person([doctor])) };

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("My patients (M6a-P6, decision 5A)", () => {
  it("lists the patients I saw, latest visit first, each opening their profile", async () => {
    const api = mockApi({ ...routes, [URL]: () => json(200, { items: [mine()], limit: 50, offset: 0 }) });
    renderInWorkspace(<MyPatients />);

    const row = await screen.findByRole("row", { name: /Bina Shah/ }, { timeout: 5000 });
    expect(row).toHaveTextContent("SC-0004");
    expect(row).toHaveTextContent("about 47 years · Female");
    expect(row).toHaveTextContent("20 Oct 2026, 10:30 IST");
    expect(row).toHaveTextContent("3");
    expect(within(row).getByRole("link", { name: "Bina Shah" })).toHaveAttribute("href", `/patients/${PATIENT_ID}`);
    const call = api.calls.find((c) => c.path === "/api/v1/my-patients");
    expect([call?.search.get("limit"), call?.search.get("offset"), call?.search.get("q")]).toEqual(["50", "0", null]);
  });

  it("searches within my patients", async () => {
    const api = mockApi({
      ...routes,
      [URL]: (call) =>
        json(200, { items: call.search.get("q") === "bin" ? [mine()] : [], limit: 50, offset: 0 }),
    });
    renderInWorkspace(<MyPatients />);
    expect(await screen.findByText("You have not seen any patients here yet.", undefined, { timeout: 5000 })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Find one of my patients"), { target: { value: " bin " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByRole("row", { name: /Bina Shah/ })).toBeInTheDocument();
    expect(api.calls.at(-1)?.search.get("q")).toBe("bin");
  });

  it("explains, with the Ref, when I have no doctor profile", async () => {
    mockApi({
      ...routes,
      [URL]: () =>
        apiError(409, "CLN_NO_DOCTOR_PROFILE", "You have no doctor profile in this clinic. The owner can link one on the Team page."),
    });
    renderInWorkspace(<MyPatients />);

    const alert = await screen.findByRole("alert", undefined, { timeout: 5000 });
    expect(alert).toHaveTextContent("You have no doctor profile in this clinic.");
    expect(alert).toHaveTextContent("Ref: test-ref");
  });
});
