import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { push, resetNavigation } from "@/test/navigation";

import { PatientResults } from "./PatientResults";
import { OTHER_ID, PATIENT_ID, patient, renderInWorkspace, workspaceRoutes } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const REGISTER = "POST /api/v1/patients";
const candidates = [
  { id: OTHER_ID, code: "SC-0001", full_name: "Asha Rao", age_years: 36 },
  { id: "0192f0a0-0000-7000-8000-0000000000c3", code: "SC-0003", full_name: "Meera Rao", age_years: 6 },
];
const phoneExists = () =>
  apiError(409, "PAT_PHONE_EXISTS", "This clinic already has patients on that phone number.", {}, { candidates });

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  vi.useRealTimers();
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

async function openDrawer() {
  renderInWorkspace(<PatientResults q="" />);
  const header = await screen.findByRole("banner");
  fireEvent.click(await within(header).findByRole("button", { name: "Register patient" }));
  return screen.findByRole("dialog", { name: "Register patient" });
}

function type(dialog: HTMLElement, label: string | RegExp, value: string) {
  fireEvent.change(within(dialog).getByLabelText(label), { target: { value } });
}

function fillAdult(dialog: HTMLElement) {
  type(dialog, /^Full name/, "Sample Person");
  type(dialog, "Date of birth", "1990-05-17");
  type(dialog, /^Phone/, "090000 00101");
  fireEvent.change(within(dialog).getByLabelText("Sex"), { target: { value: "FEMALE" } });
}

const submit = (dialog: HTMLElement) =>
  fireEvent.click(within(dialog).getByRole("button", { name: "Register patient" }));

describe("register patient drawer", () => {
  it("FR-PAT-01: registers with a date of birth and opens the new profile", async () => {
    const api = mockApi({ ...workspaceRoutes, [REGISTER]: () => json(201, patient()) });
    const dialog = await openDrawer();

    fillAdult(dialog);
    submit(dialog);

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/patients/${PATIENT_ID}`));
    const sent = api.calls.find((c) => c.method === "POST" && c.path === "/api/v1/patients");
    expect(sent?.body).toEqual({
      full_name: "Sample Person",
      phone: "090000 00101",
      sex: "FEMALE",
      date_of_birth: "1990-05-17",
      guardian_name: null,
      language: "en",
      confirm_new: false,
    });
    expect(sent?.headers.get("X-CSRF-Token")).toBe("csrf-token");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("FR-PAT-06, R3: an age under 18 shows the guardian field and makes the phone the guardian's", async () => {
    mockApi(workspaceRoutes);
    const dialog = await openDrawer();
    expect(within(dialog).queryByLabelText(/Parent or guardian's name/)).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("radio", { name: "Only the age is known" }));
    type(dialog, /^Age in years/, "6");

    expect(within(dialog).getByLabelText(/^Parent or guardian's name/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^Parent or guardian's phone/)).toBeInTheDocument();
  });

  it("FR-PAT-06: the age hint uses the clinic's date: 18 today in Kolkata is an adult while UTC is still on yesterday", async () => {
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-10-16T19:00:00Z") }); // 00:30, 17 Oct IST
    mockApi(workspaceRoutes);
    const dialog = await openDrawer();

    type(dialog, "Date of birth", "2008-10-17");
    expect(within(dialog).queryByLabelText(/Parent or guardian's name/)).not.toBeInTheDocument();
    type(dialog, "Date of birth", "2008-10-18");
    expect(within(dialog).getByLabelText(/^Parent or guardian's name/)).toBeInTheDocument();
  });

  it("AC2: PAT_GUARDIAN_REQUIRED lands on the guardian field", async () => {
    mockApi({
      ...workspaceRoutes,
      [REGISTER]: () => apiError(422, "PAT_GUARDIAN_REQUIRED", "A patient under 18 needs a parent or guardian."),
    });
    const dialog = await openDrawer();
    fillAdult(dialog);
    submit(dialog);

    const guardian = await within(dialog).findByLabelText(/^Parent or guardian's name/);
    expect(guardian).toHaveAttribute("aria-invalid", "true");
    expect(within(dialog).getByText("A patient under 18 needs a parent or guardian.")).toBeInTheDocument();
    await waitFor(() => expect(guardian).toHaveFocus());
  });

  it("R1: PAT_PHONE_INVALID lands on the phone field", async () => {
    mockApi({
      ...workspaceRoutes,
      [REGISTER]: () =>
        apiError(422, "PAT_PHONE_INVALID", "That is not a valid phone number.", {}, {
          fields: [{ field: "phone", reason: "is not a valid phone number" }],
        }),
    });
    const dialog = await openDrawer();
    fillAdult(dialog);
    submit(dialog);

    expect(await within(dialog).findByText("is not a valid phone number")).toBeInTheDocument();
    expect(within(dialog).getByLabelText(/^Phone/)).toHaveAttribute("aria-invalid", "true");
  });

  it("FR-PAT-02, AC1: a phone already in the clinic lists its patients; Use this patient opens one", async () => {
    mockApi({ ...workspaceRoutes, [REGISTER]: phoneExists });
    const dialog = await openDrawer();
    fillAdult(dialog);
    submit(dialog);

    expect(await within(dialog).findByText("This phone number is already registered")).toBeInTheDocument();
    expect(within(dialog).getByText("Meera Rao")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Use this patient: Asha Rao, SC-0001" }));

    expect(push).toHaveBeenCalledWith(`/patients/${OTHER_ID}`);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("FR-PAT-02, D3: Register as a new family member resends the same details with confirm_new", async () => {
    const api = mockApi({ ...workspaceRoutes, [REGISTER]: [phoneExists, () => json(201, patient())] });
    const dialog = await openDrawer();
    fillAdult(dialog);
    submit(dialog);

    fireEvent.click(await within(dialog).findByRole("button", { name: "Register as a new family member" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/patients/${PATIENT_ID}`));
    const bodies = api.calls.filter((c) => c.method === "POST" && c.path === "/api/v1/patients").map((c) => c.body);
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual({ ...(bodies[0] as object), confirm_new: true });
  });

  it("Back to the form keeps what was typed", async () => {
    mockApi({ ...workspaceRoutes, [REGISTER]: phoneExists });
    const dialog = await openDrawer();
    fillAdult(dialog);
    submit(dialog);
    fireEvent.click(await within(dialog).findByRole("button", { name: "Back to the form" }));

    expect(within(dialog).getByLabelText(/^Full name/)).toHaveValue("Sample Person");
  });

  it("a double click registers once: the button is disabled while sending", async () => {
    let release: (response: Response) => void = () => undefined;
    const api = mockApi({
      ...workspaceRoutes,
      [REGISTER]: () => new Promise<Response>((resolve) => (release = resolve)),
    });
    const dialog = await openDrawer();
    fillAdult(dialog);
    submit(dialog);

    const button = await within(dialog).findByRole("button", { name: "Registering…" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    release(json(201, patient()));

    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(api.count(REGISTER)).toBe(1);
  });

  it("Close leaves without registering", async () => {
    const api = mockApi(workspaceRoutes);
    const dialog = await openDrawer();
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(api.count(REGISTER)).toBe(0);
  });
});
