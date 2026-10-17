import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi, type Recorded } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { PatientProfile } from "./PatientProfile";
import { PATIENT_ID, patient, renderInWorkspace, workspaceRoutes } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const ONE = `/api/v1/patients/${PATIENT_ID}`;
const GET = `GET ${ONE}`;

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

function renderProfile() {
  renderInWorkspace(<PatientProfile patientId={PATIENT_ID} />);
  // The first render of the file is the slowest under a full parallel run; 5 s as elsewhere.
  return screen.findByRole("heading", { level: 1 }, { timeout: 5000 });
}

const consent = () => screen.getByRole("region", { name: "Messages" });

describe("patient profile", () => {
  it("FR-PAT-03: shows the code, the phone in full for dialling, an estimated age and 'Not asked yet'", async () => {
    mockApi({ ...workspaceRoutes, [GET]: () => json(200, patient()) });

    expect(await renderProfile()).toHaveTextContent("Bina Shah");
    expect(screen.getByText("SC-0004")).toBeInTheDocument();
    expect(screen.getByText(/about 47 years/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+91 90000 00102" })).toHaveAttribute("href", "tel:+919000000102");
    expect(screen.getByTestId("consent-summary")).toHaveTextContent("Not asked yet");
  });

  it("FR-PAT-06: a minor shows the guardian and the guardian's phone", async () => {
    mockApi({
      ...workspaceRoutes,
      [GET]: () => json(200, patient({ is_minor: true, guardian_name: "Asha Rao", age_years: 6, age_is_estimated: false })),
    });
    await renderProfile();

    expect(screen.getByText("Parent or guardian's phone")).toBeInTheDocument();
    expect(screen.getByText("Asha Rao")).toBeInTheDocument();
  });

  it("AC7, R8: another clinic's patient reads the same as an unknown one", async () => {
    mockApi({ ...workspaceRoutes, [GET]: () => apiError(404, "REQ_NOT_FOUND", "Not found.") });

    expect(await renderProfile()).toHaveTextContent("Patient not found");
  });

  it("R7: Edit details sends only what changed, and there is no field for the code", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      [GET]: () => json(200, patient()),
      [`PATCH ${ONE}`]: () => json(200, patient({ full_name: "Bina Shah Mehta" })),
    });
    await renderProfile();

    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    expect(screen.queryByDisplayValue("SC-0004")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Full name/), { target: { value: "Bina Shah Mehta" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Bina Shah Mehta" })).toBeInTheDocument();
    const sent = api.calls.find((c) => c.method === "PATCH");
    expect(sent?.body).toEqual({ full_name: "Bina Shah Mehta" });
    expect(sent?.headers.get("X-CSRF-Token")).toBe("csrf-token");
  });

  it("an edit that changes nothing sends nothing", async () => {
    const api = mockApi({ ...workspaceRoutes, [GET]: () => json(200, patient()) });
    await renderProfile();

    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("button", { name: "Edit details" })).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "PATCH")).toBe(false);
  });
});

describe("consent, opt-out and opt-in (FR-PAT-05, FR-MSG-05)", () => {
  it("FR-PAT-05: records the answer with PUT and shows what is allowed", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      [GET]: () => json(200, patient()),
      [`PUT ${ONE}/consent`]: () =>
        json(200, patient({ whatsapp_consent: true, whatsapp_allowed: true, consent_recorded_at: "2026-10-17T04:00:00Z" })),
    });
    await renderProfile();

    fireEvent.click(within(consent()).getByRole("button", { name: "Record consent" }));
    expect(within(consent()).getByText(/Ask the patient:/)).toBeInTheDocument();
    fireEvent.click(within(consent()).getByRole("checkbox", { name: "WhatsApp: yes" }));
    fireEvent.click(within(consent()).getByRole("button", { name: "Save answer" }));

    expect(await screen.findByText("Allowed: WhatsApp")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({ whatsapp: true, sms: false });
    expect(screen.getByText(/Recorded 17 Oct 2026/)).toBeInTheDocument();
  });

  it("R6: asked and declined is not the same as never asked", async () => {
    mockApi({ ...workspaceRoutes, [GET]: () => json(200, patient({ consent_recorded_at: "2026-10-17T04:00:00Z" })) });
    await renderProfile();

    expect(screen.getByTestId("consent-summary")).toHaveTextContent("Declined");
    expect(within(consent()).getByRole("button", { name: "Change consent" })).toBeInTheDocument();
  });

  it("FR-PAT-06: for a minor the script asks the parent or guardian", async () => {
    mockApi({ ...workspaceRoutes, [GET]: () => json(200, patient({ is_minor: true, guardian_name: "Asha Rao" })) });
    await renderProfile();

    fireEvent.click(within(consent()).getByRole("button", { name: "Record consent" }));
    expect(within(consent()).getByText(/Ask the parent or guardian:/)).toBeInTheDocument();
  });

  it("AC5: opt-out needs a confirmation; then only Opt back in is offered, and it takes the new answer", async () => {
    const opted = patient({ opted_out: true, opted_out_at: "2026-10-17T05:00:00Z", whatsapp_consent: true });
    const api = mockApi({
      ...workspaceRoutes,
      [GET]: () => json(200, patient({ whatsapp_consent: true, whatsapp_allowed: true, consent_recorded_at: "2026-10-17T04:00:00Z" })),
      [`POST ${ONE}/opt-out`]: () => json(200, opted),
      [`POST ${ONE}/opt-in`]: () =>
        json(200, patient({ sms_consent: true, sms_allowed: true, consent_recorded_at: "2026-10-17T06:00:00Z" })),
    });
    await renderProfile();

    fireEvent.click(within(consent()).getByRole("button", { name: "Opt out of all messages" }));
    expect(api.calls.some((c) => c.path.endsWith("/opt-out"))).toBe(false);
    fireEvent.click(within(consent()).getByRole("button", { name: "Yes, opt out" }));

    expect(await screen.findByText("Opted out: no messages")).toBeInTheDocument();
    expect(within(consent()).queryByRole("button", { name: /consent/ })).not.toBeInTheDocument();
    fireEvent.click(within(consent()).getByRole("button", { name: "Opt back in" }));
    expect(within(consent()).getByRole("checkbox", { name: "WhatsApp: yes" })).not.toBeChecked();
    fireEvent.click(within(consent()).getByRole("checkbox", { name: "SMS: yes" }));
    fireEvent.click(within(consent()).getByRole("button", { name: "Opt back in" }));

    expect(await screen.findByText("Allowed: SMS")).toBeInTheDocument();
    const optIn = api.calls.find((c: Recorded) => c.path.endsWith("/opt-in"));
    expect(optIn?.body).toEqual({ whatsapp: false, sms: true });
  });

  it("PAT_OPTED_OUT from a stale screen is explained and the screen catches up", async () => {
    const api = mockApi({
      ...workspaceRoutes,
      [GET]: [() => json(200, patient()), () => json(200, patient({ opted_out: true, opted_out_at: "2026-10-17T05:00:00Z" }))],
      [`PUT ${ONE}/consent`]: () =>
        apiError(409, "PAT_OPTED_OUT", "This patient asked not to be messaged. Opt them back in first."),
    });
    await renderProfile();

    fireEvent.click(within(consent()).getByRole("button", { name: "Record consent" }));
    fireEvent.click(within(consent()).getByRole("button", { name: "Save answer" }));

    expect(await within(consent()).findByRole("alert")).toHaveTextContent("Opt them back in first.");
    await waitFor(() => expect(within(consent()).getByRole("button", { name: "Opt back in" })).toBeInTheDocument());
    expect(api.count(GET)).toBe(2);
  });
});
